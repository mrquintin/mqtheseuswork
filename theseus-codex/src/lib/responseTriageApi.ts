/**
 * Response-triage helpers for the founder workspace.
 *
 * The authoritative classifier lives in
 * `noosphere/noosphere/literature/response_triage.py` (Python, with the
 * firm's LLM client). This module is the codex-side bridge:
 *
 *   - `seedTriageRow` runs a deliberately small JS heuristic at
 *     submission time so the queue always has a row to render. It
 *     mirrors the four-label schema from the Python classifier and
 *     records `usedLlm = false`. The Python pass refines the row
 *     later (offline / scheduled) and overwrites `label`,
 *     `impliedObjection`, etc.
 *
 *   - `listTriageQueue` powers the founder queue page. Substantive
 *     responses surface first, ordered by cached severity descending.
 *     Spam_noise is filtered unless `includeArchived` is set.
 *
 *   - `getTriageDetail` powers the per-response detail view. It joins
 *     the original PublicResponse, the triage row, any existing reply,
 *     and the conclusion title.
 *
 * The Python and JS code share the four-label / six-spam-reason
 * vocabulary by string. Don't drift them.
 */

import { db } from "@/lib/db";
import { parsePublicationPayload } from "@/lib/conclusionsRead";

export const TRIAGE_LABELS = [
  "SUBSTANTIVE_OBJECTION",
  "CLARIFICATION_REQUEST",
  "GENERAL_ENGAGEMENT",
  "SPAM_NOISE",
] as const;
export type TriageLabel = (typeof TRIAGE_LABELS)[number];

export const SPAM_REASONS = [
  "",
  "too_short",
  "promotional_link",
  "off_topic",
  "abusive_language",
  "repeat_sender",
  "low_information",
] as const;
export type SpamReason = (typeof SPAM_REASONS)[number];

export const REPLY_VISIBILITIES = ["private", "public"] as const;
export type ReplyVisibility = (typeof REPLY_VISIBILITIES)[number];

const MIN_BODY_CHARS = 20;

const PROMO_TOKENS = [
  "click here",
  "buy now",
  "free trial",
  "make money",
  "subscribe to",
  "limited time",
  "viagra",
  "casino",
  "crypto giveaway",
];

const ABUSE_TOKENS = ["idiot", "moron", "shut up", "garbage"];

const OBJECTION_TOKENS = [
  "however",
  "but ",
  "disagree",
  "incorrect",
  "wrong",
  "evidence shows",
  "data show",
  "contradict",
  "actually",
  "fails to",
  "overlook",
  "ignores",
  "the study",
];

const CLARIFICATION_TOKENS = [
  "could you clarify",
  "what do you mean",
  "can you explain",
];

export type SeedTriageInput = {
  responseId: string;
  organizationId: string;
  kind: string;
  body: string;
  citationUrl: string;
  submitterEmail: string;
};

export type SeedTriageOutput = {
  label: TriageLabel;
  spamReason: SpamReason;
  confidence: number;
  rationale: string;
  senderHash: string;
  elevatedSenderFlag: boolean;
};

/**
 * Compute and persist a `ResponseTriage` row for a freshly submitted
 * PublicResponse. Idempotent — calling twice on the same response does
 * not duplicate (we use upsert against the unique `publicResponseId`).
 *
 * The heuristic is intentionally minimal. The Python pass is the
 * authority; this exists so the queue is never empty between
 * submission and the next classifier run.
 */
export async function seedTriageRow(input: SeedTriageInput): Promise<SeedTriageOutput> {
  const verdict = jsHeuristic(input);
  const senderHash = input.submitterEmail
    ? await sha256Hex(input.submitterEmail.trim().toLowerCase())
    : "";

  const elevated = senderHash ? await senderSpamCount(senderHash, input.organizationId) >= 2 : false;
  let spamReason = verdict.spamReason;
  if (verdict.label === "SPAM_NOISE" && elevated && (spamReason === "" || spamReason === "low_information")) {
    spamReason = "repeat_sender";
  }
  if (verdict.label !== "SPAM_NOISE") spamReason = "";

  await db.responseTriage.upsert({
    where: { publicResponseId: input.responseId },
    create: {
      organizationId: input.organizationId,
      publicResponseId: input.responseId,
      label: verdict.label,
      spamReason,
      confidence: verdict.confidence,
      rationale: verdict.rationale,
      usedLlm: false,
      senderHash,
      elevatedSenderFlag: elevated,
      severityValue: verdict.label === "SUBSTANTIVE_OBJECTION" ? 0.5 : 0,
    },
    update: {
      label: verdict.label,
      spamReason,
      confidence: verdict.confidence,
      rationale: verdict.rationale,
      senderHash,
      elevatedSenderFlag: elevated,
    },
  });

  return {
    label: verdict.label,
    spamReason,
    confidence: verdict.confidence,
    rationale: verdict.rationale,
    senderHash,
    elevatedSenderFlag: elevated,
  };
}

function jsHeuristic(input: SeedTriageInput): {
  label: TriageLabel;
  spamReason: SpamReason;
  confidence: number;
  rationale: string;
} {
  const body = (input.body || "").replace(/\s+/g, " ").trim();
  const lower = body.toLowerCase();
  const charN = body.length;

  if (charN < MIN_BODY_CHARS) {
    return {
      label: "SPAM_NOISE",
      spamReason: "too_short",
      confidence: 0.95,
      rationale: `body length ${charN} < ${MIN_BODY_CHARS}`,
    };
  }
  for (const t of PROMO_TOKENS) {
    if (lower.includes(t)) {
      return { label: "SPAM_NOISE", spamReason: "promotional_link", confidence: 0.9, rationale: `promo: ${t}` };
    }
  }
  for (const t of ABUSE_TOKENS) {
    if (lower.includes(t)) {
      return { label: "SPAM_NOISE", spamReason: "abusive_language", confidence: 0.75, rationale: `abuse: ${t}` };
    }
  }

  const kindPriors: Record<string, TriageLabel> = {
    counter_evidence: "SUBSTANTIVE_OBJECTION",
    counter_argument: "SUBSTANTIVE_OBJECTION",
    clarification: "CLARIFICATION_REQUEST",
    agreement_extension: "GENERAL_ENGAGEMENT",
  };
  const prior: TriageLabel = kindPriors[input.kind] ?? "GENERAL_ENGAGEMENT";

  const hasQuestion = body.includes("?");
  const objHit = OBJECTION_TOKENS.some((t) => lower.includes(t));
  const clarHit = CLARIFICATION_TOKENS.some((t) => lower.includes(t));
  const hasCitation = input.citationUrl.trim().length > 0;
  const longBody = charN >= 200;

  const score: Record<TriageLabel, number> = {
    SUBSTANTIVE_OBJECTION: 0,
    CLARIFICATION_REQUEST: 0,
    GENERAL_ENGAGEMENT: 0,
    SPAM_NOISE: 0,
  };
  score[prior] += 0.35;
  if (objHit) score.SUBSTANTIVE_OBJECTION += 0.3;
  if (hasCitation) score.SUBSTANTIVE_OBJECTION += 0.2;
  if (longBody) score.SUBSTANTIVE_OBJECTION += 0.15;
  if (hasQuestion) score.CLARIFICATION_REQUEST += 0.3;
  if (clarHit) score.CLARIFICATION_REQUEST += 0.25;
  if (!objHit && !hasQuestion && !clarHit) score.GENERAL_ENGAGEMENT += 0.2;

  let label: TriageLabel = "GENERAL_ENGAGEMENT";
  let best = -1;
  for (const k of TRIAGE_LABELS) {
    if (score[k] > best) {
      best = score[k];
      label = k;
    }
  }

  if (label === "GENERAL_ENGAGEMENT" && charN < MIN_BODY_CHARS * 2 && !hasCitation) {
    return {
      label: "SPAM_NOISE",
      spamReason: "low_information",
      confidence: 0.6,
      rationale: "short engagement-only body, no question, no citation",
    };
  }

  return {
    label,
    spamReason: "",
    confidence: Math.max(0, Math.min(1, best)),
    rationale: `chars=${charN}; prior=${prior}; q=${hasQuestion}; obj=${objHit}; cite=${hasCitation}`,
  };
}

async function sha256Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function senderSpamCount(senderHash: string, organizationId: string): Promise<number> {
  return db.responseTriage.count({
    where: {
      organizationId,
      senderHash,
      label: "SPAM_NOISE",
    },
  });
}

// ── queue + detail readers ───────────────────────────────────────────

export type TriageQueueRow = {
  id: string;
  responseId: string;
  label: TriageLabel;
  effectiveLabel: TriageLabel;
  spamReason: SpamReason;
  confidence: number;
  severityValue: number;
  impliedObjection: string;
  rationale: string;
  archivedAt: Date | null;
  archiveNote: string;
  elevatedSenderFlag: boolean;
  createdAt: Date;
  publicResponse: {
    id: string;
    kind: string;
    body: string;
    citationUrl: string;
    submitterEmail: string;
    pseudonymous: boolean;
    publishConsent: boolean;
    createdAt: Date;
    seenAt: Date | null;
  };
  conclusion: {
    id: string;
    slug: string;
    version: number;
    title: string;
  };
  reply: {
    id: string;
    visibility: ReplyVisibility;
    publishConfirmed: boolean;
    promotedToReview: boolean;
    triggeredRevisionId: string | null;
  } | null;
};

export type TriageQueueFilter = {
  organizationId: string;
  /** When false (default) excludes SPAM_NOISE and archived rows. */
  includeNoise?: boolean;
  includeArchived?: boolean;
  limit?: number;
};

type RawTriageRow = Awaited<ReturnType<typeof loadRawRows>>[number];

async function loadRawRows(filter: TriageQueueFilter) {
  return db.responseTriage.findMany({
    where: {
      organizationId: filter.organizationId,
      ...(filter.includeArchived ? {} : { archivedAt: null }),
    },
    orderBy: [
      { severityValue: "desc" },
      { createdAt: "desc" },
    ],
    take: filter.limit ?? 200,
    include: {
      publicResponse: {
        include: {
          published: {
            select: { id: true, slug: true, version: true, payloadJson: true },
          },
          publicReply: {
            select: {
              id: true,
              visibility: true,
              publishConfirmed: true,
              promotedToReview: true,
              triggeredRevisionId: true,
            },
          },
        },
      },
    },
  });
}

export async function listTriageQueue(filter: TriageQueueFilter): Promise<TriageQueueRow[]> {
  const rows = await loadRawRows(filter);
  const includeNoise = filter.includeNoise ?? false;
  return rows
    .map(toQueueRow)
    .filter((row) => includeNoise || row.effectiveLabel !== "SPAM_NOISE");
}

export async function getTriageDetail(
  organizationId: string,
  triageId: string,
): Promise<TriageQueueRow | null> {
  const row = await db.responseTriage.findFirst({
    where: { id: triageId, organizationId },
    include: {
      publicResponse: {
        include: {
          published: {
            select: { id: true, slug: true, version: true, payloadJson: true },
          },
          publicReply: {
            select: {
              id: true,
              visibility: true,
              publishConfirmed: true,
              promotedToReview: true,
              triggeredRevisionId: true,
            },
          },
        },
      },
    },
  });
  if (!row) return null;
  return toQueueRow(row);
}

export async function getReplyBody(
  organizationId: string,
  triageId: string,
): Promise<string | null> {
  const row = await db.responseTriage.findFirst({
    where: { id: triageId, organizationId },
    select: {
      publicResponse: {
        select: { publicReply: { select: { body: true } } },
      },
    },
  });
  return row?.publicResponse?.publicReply?.body ?? null;
}

function toQueueRow(row: RawTriageRow): TriageQueueRow {
  const label = (row.label as TriageLabel) ?? "GENERAL_ENGAGEMENT";
  const effectiveLabel = ((row.manualLabel as TriageLabel) || label) as TriageLabel;
  const spamReason = (row.manualReason || row.spamReason || "") as SpamReason;
  const conclusion = parsePublicationPayload({
    payloadJson: row.publicResponse.published.payloadJson,
    slug: row.publicResponse.published.slug,
  });
  return {
    id: row.id,
    responseId: row.publicResponseId,
    label,
    effectiveLabel,
    spamReason,
    confidence: row.confidence,
    severityValue: row.severityValue,
    impliedObjection: row.impliedObjection,
    rationale: row.rationale,
    archivedAt: row.archivedAt,
    archiveNote: row.archiveNote,
    elevatedSenderFlag: row.elevatedSenderFlag,
    createdAt: row.createdAt,
    publicResponse: {
      id: row.publicResponse.id,
      kind: row.publicResponse.kind,
      body: row.publicResponse.body,
      citationUrl: row.publicResponse.citationUrl,
      submitterEmail: row.publicResponse.submitterEmail,
      pseudonymous: row.publicResponse.pseudonymous,
      publishConsent: row.publicResponse.publishConsent,
      createdAt: row.publicResponse.createdAt,
      seenAt: row.publicResponse.seenAt,
    },
    conclusion: {
      id: row.publicResponse.published.id,
      slug: row.publicResponse.published.slug,
      version: row.publicResponse.published.version,
      title: conclusion.conclusionText,
    },
    reply: row.publicResponse.publicReply
      ? {
          id: row.publicResponse.publicReply.id,
          visibility: row.publicResponse.publicReply.visibility as ReplyVisibility,
          publishConfirmed: row.publicResponse.publicReply.publishConfirmed,
          promotedToReview: row.publicResponse.publicReply.promotedToReview,
          triggeredRevisionId: row.publicResponse.publicReply.triggeredRevisionId,
        }
      : null,
  };
}

// ── public-article surface ───────────────────────────────────────────

export type ReaderResponseEntry = {
  responseId: string;
  responderLabel: string;
  responseBody: string;
  responseCitationUrl: string;
  replyBody: string;
  repliedAt: Date;
};

/**
 * The "Reader responses" appendix payload for a single published
 * conclusion. Returns only entries where:
 *   - the responder consented to publication
 *   - the founder confirmed `visibility=public` AND `publishConfirmed=true`
 *   - the underlying response is not in `rejected` / `archived` state
 */
export async function listPublicReaderResponses(
  organizationId: string,
  publishedConclusionId: string,
): Promise<ReaderResponseEntry[]> {
  const rows = await db.publicReply.findMany({
    where: {
      organizationId,
      visibility: "public",
      publishConfirmed: true,
      publicResponse: {
        publishedConclusionId,
        publishConsent: true,
        status: { notIn: ["rejected", "archived"] },
      },
    },
    orderBy: { publishConfirmedAt: "desc" },
    include: {
      publicResponse: {
        select: {
          id: true,
          body: true,
          citationUrl: true,
          submitterEmail: true,
          orcid: true,
          pseudonymous: true,
        },
      },
    },
  });

  return rows.map((row) => ({
    responseId: row.publicResponse.id,
    responderLabel: respondentDisplay(row.publicResponse),
    responseBody: row.publicResponse.body,
    responseCitationUrl: row.publicResponse.citationUrl,
    replyBody: row.body,
    repliedAt: row.publishConfirmedAt ?? row.updatedAt,
  }));
}

function respondentDisplay(resp: {
  pseudonymous: boolean;
  submitterEmail: string;
  orcid: string;
}): string {
  if (resp.pseudonymous) return resp.orcid ? `Reader (ORCID ${resp.orcid})` : "Reader";
  // We never expose the raw email — the public surface gets the
  // localpart only, so a poster's domain doesn't leak.
  const at = resp.submitterEmail.indexOf("@");
  if (at <= 0) return "Reader";
  return resp.submitterEmail.slice(0, at);
}
