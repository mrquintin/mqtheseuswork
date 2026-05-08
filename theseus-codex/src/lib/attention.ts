import { db } from "@/lib/db";
import type { TenantContext } from "@/lib/tenant";

/**
 * Unified founder attention queue.
 *
 * The dashboard's primary surface aggregates "what needs your attention
 * right now" across every founder-side queue (drift events, peer-review
 * escalations, source-triage, response triage, open questions, citation
 * verdicts, retraction propagations, calibration breaches). Each queue
 * has a small fetcher below; `gatherAttentionItems` runs them in
 * parallel, applies the founder's snooze/dismiss state, and ranks the
 * survivors.
 *
 * Ranking rule (spec): severity > age > queue identity. Within the
 * same severity tier an older item ranks above a fresher one — i.e.
 * a high-severity item sitting for a week beats a freshly-arrived
 * high-severity item — but severity always dominates age across tiers.
 *
 * Snooze cap: 14 days. Anything longer is rewritten on the API layer
 * as a dismissal with reason "deferred indefinitely".
 */

export const ATTENTION_QUEUES = [
  "drift",
  "peer_review",
  "source_triage",
  "response_triage",
  "open_question",
  "citation_verdict",
  "retraction_propagation",
  "calibration_breach",
] as const;

export type AttentionQueueId = (typeof ATTENTION_QUEUES)[number];

export const ATTENTION_QUEUE_LABELS: Record<AttentionQueueId, string> = {
  drift: "Drift",
  peer_review: "Peer review",
  source_triage: "Source triage",
  response_triage: "Response triage",
  open_question: "Open questions",
  citation_verdict: "Citation verdicts",
  retraction_propagation: "Retraction propagation",
  calibration_breach: "Calibration breach",
};

export type AttentionSeverity = "low" | "medium" | "high";

export type AttentionItem = {
  queue: AttentionQueueId;
  queueLabel: string;
  itemId: string;
  severity: AttentionSeverity;
  createdAt: Date;
  preview: string;
  link: string;
};

export type AttentionItemAction = {
  action: "snooze" | "dismiss" | "unsnooze";
  snoozedUntil: Date | null;
  reason: string;
  createdAt: Date;
};

export type AttentionItemActionRow = AttentionItemAction & {
  queue: AttentionQueueId;
  itemId: string;
};

export const MAX_SNOOZE_DAYS = 14;
export const MAX_SNOOZE_MS = MAX_SNOOZE_DAYS * 24 * 60 * 60 * 1000;
export const DISMISS_REASON_DEFERRED = "deferred indefinitely";

export function severityRank(severity: AttentionSeverity): number {
  if (severity === "high") return 2;
  if (severity === "medium") return 1;
  return 0;
}

/**
 * Rank items by (severity desc, age desc, queue id asc). Older items
 * within the same severity tier come first; queue id is just a stable
 * tie-breaker.
 */
export function rankAttentionItems(
  items: AttentionItem[],
  now: Date = new Date(),
): AttentionItem[] {
  return [...items].sort((a, b) => {
    const sev = severityRank(b.severity) - severityRank(a.severity);
    if (sev !== 0) return sev;
    const ageA = now.getTime() - a.createdAt.getTime();
    const ageB = now.getTime() - b.createdAt.getTime();
    if (ageA !== ageB) return ageB - ageA;
    if (a.queue !== b.queue) return a.queue < b.queue ? -1 : 1;
    return a.itemId < b.itemId ? -1 : a.itemId > b.itemId ? 1 : 0;
  });
}

/**
 * Drop items the founder has dismissed or whose active snooze has not
 * expired. The "current state" of an item is the latest action row
 * (by createdAt) for that (queue, itemId); an "unsnooze" cancels a
 * prior snooze, and a snooze whose `snoozedUntil` is in the past is
 * effectively expired and the item resurfaces on its own.
 */
export function applyFounderActions(
  items: AttentionItem[],
  actions: AttentionItemActionRow[],
  now: Date = new Date(),
): AttentionItem[] {
  const latest = new Map<string, AttentionItemActionRow>();
  for (const row of actions) {
    const key = actionKey(row.queue, row.itemId);
    const prior = latest.get(key);
    if (!prior || row.createdAt.getTime() > prior.createdAt.getTime()) {
      latest.set(key, row);
    }
  }
  return items.filter((item) => {
    const row = latest.get(actionKey(item.queue, item.itemId));
    if (!row) return true;
    if (row.action === "dismiss") return false;
    if (row.action === "snooze") {
      if (!row.snoozedUntil) return false;
      return row.snoozedUntil.getTime() <= now.getTime();
    }
    return true;
  });
}

function actionKey(queue: AttentionQueueId, itemId: string): string {
  return `${queue}::${itemId}`;
}

/**
 * Translate a requested snooze into either a snooze (clamped to the 14-day
 * cap) or a dismissal with reason "deferred indefinitely". Per spec, a
 * caller asking for >14 days has stopped triaging the item — record it
 * as a dismissal so the dismissal-rate signal still picks it up.
 */
export function resolveSnoozeRequest(
  rawSnoozedUntil: Date,
  now: Date = new Date(),
):
  | { kind: "snooze"; snoozedUntil: Date }
  | { kind: "dismiss"; reason: string } {
  const max = new Date(now.getTime() + MAX_SNOOZE_MS);
  if (rawSnoozedUntil.getTime() <= now.getTime()) {
    return { kind: "snooze", snoozedUntil: new Date(now.getTime() + 60_000) };
  }
  if (rawSnoozedUntil.getTime() > max.getTime()) {
    return { kind: "dismiss", reason: DISMISS_REASON_DEFERRED };
  }
  return { kind: "snooze", snoozedUntil: rawSnoozedUntil };
}

// ── Queue fetchers ─────────────────────────────────────────────────────
//
// Each fetcher is wrapped in its own try/catch in `gatherAttentionItems`
// so a single broken table (schema lag in dev, an unmigrated test DB)
// doesn't blank the whole dashboard. Severity mapping per queue is
// documented inline.

async function fetchDriftItems(tenant: TenantContext): Promise<AttentionItem[]> {
  const rows = await db.driftEvent.findMany({
    where: {
      organizationId: tenant.organizationId,
      // Method drift gets its own queue; principle drift lands here.
      OR: [{ targetKind: "principle" }, { targetKind: { equals: null } as never }],
    },
    orderBy: { observedAt: "desc" },
    take: 50,
  });
  return rows.map((row) => ({
    queue: "drift" as const,
    queueLabel: ATTENTION_QUEUE_LABELS.drift,
    itemId: row.id,
    severity: driftScoreSeverity(row.driftScore),
    createdAt: row.observedAt,
    preview:
      row.naturalLanguageSummary ||
      row.notes ||
      `Drift score ${(row.driftScore * 100).toFixed(0)}% on ${row.targetKind} ${row.targetId.slice(0, 8)}`,
    link: `/ops?panel=drift#${row.id}`,
  }));
}

async function fetchCalibrationBreachItems(
  tenant: TenantContext,
): Promise<AttentionItem[]> {
  const rows = await db.driftEvent.findMany({
    where: {
      organizationId: tenant.organizationId,
      targetKind: "method",
    },
    orderBy: { observedAt: "desc" },
    take: 50,
  });
  return rows.map((row) => ({
    queue: "calibration_breach" as const,
    queueLabel: ATTENTION_QUEUE_LABELS.calibration_breach,
    itemId: row.id,
    severity: methodSeverityToAttention(row.severity),
    createdAt: row.observedAt,
    preview:
      row.naturalLanguageSummary ||
      `Method ${row.methodName ?? "?"}@${row.methodVersion ?? "?"} drifted (${row.severity ?? "ok"})`,
    link: `/methods/${encodeURIComponent(row.methodName ?? "")}/${encodeURIComponent(row.methodVersion ?? "")}`,
  }));
}

async function fetchPeerReviewItems(
  tenant: TenantContext,
): Promise<AttentionItem[]> {
  const rows = await db.reviewItem.findMany({
    where: {
      organizationId: tenant.organizationId,
      status: "open",
    },
    orderBy: { createdAt: "desc" },
    take: 50,
  });
  return rows.map((row) => ({
    queue: "peer_review" as const,
    queueLabel: ATTENTION_QUEUE_LABELS.peer_review,
    itemId: row.id,
    severity: scalarSeverity(row.severity),
    createdAt: row.createdAt,
    preview: row.reason || `Peer-review escalation (severity ${row.severity.toFixed(2)})`,
    link: `/peer-review/${encodeURIComponent(row.id)}`,
  }));
}

async function fetchSourceTriageItems(
  tenant: TenantContext,
): Promise<AttentionItem[]> {
  const rows = await db.sourceTriageItem.findMany({
    where: {
      organizationId: tenant.organizationId,
      decision: "pending",
    },
    orderBy: { createdAt: "desc" },
    take: 100,
  });
  return rows.map((row) => {
    const isRetraction = row.trigger === "standing";
    const queue: AttentionQueueId = isRetraction
      ? "retraction_propagation"
      : "source_triage";
    return {
      queue,
      queueLabel: ATTENTION_QUEUE_LABELS[queue],
      itemId: row.id,
      severity: sourceTriageSeverity(row.status, isRetraction),
      createdAt: row.createdAt,
      preview: isRetraction
        ? `Retraction-class transition on ${row.sourceId} affects conclusion ${row.conclusionId.slice(0, 8)}`
        : `Citation-chain verdict on ${row.sourceId} affects conclusion ${row.conclusionId.slice(0, 8)}`,
      link: `/source-triage#${row.id}`,
    };
  });
}

async function fetchResponseTriageItems(
  tenant: TenantContext,
): Promise<AttentionItem[]> {
  const rows = await db.responseTriage.findMany({
    where: {
      organizationId: tenant.organizationId,
      archivedAt: null,
      // Honour founder override when present, otherwise fall back to
      // the classifier label. We surface the substantive-objection
      // tier; SPAM_NOISE and GENERAL_ENGAGEMENT live in a separate
      // inbox.
      OR: [
        { manualLabel: "SUBSTANTIVE_OBJECTION" },
        { manualLabel: "", label: "SUBSTANTIVE_OBJECTION" },
      ],
    },
    orderBy: { createdAt: "desc" },
    take: 50,
    include: {
      publicResponse: { select: { id: true, kind: true, body: true } },
    },
  });
  return rows.map((row) => ({
    queue: "response_triage" as const,
    queueLabel: ATTENTION_QUEUE_LABELS.response_triage,
    itemId: row.id,
    severity: scalarSeverity(row.severityValue),
    createdAt: row.createdAt,
    preview:
      row.impliedObjection ||
      truncate(row.publicResponse?.body ?? "", 120) ||
      "Substantive objection awaiting reply",
    link: `/responses/${encodeURIComponent(row.publicResponseId)}`,
  }));
}

async function fetchOpenQuestionItems(
  tenant: TenantContext,
): Promise<AttentionItem[]> {
  const rows = await db.openQuestion.findMany({
    where: { organizationId: tenant.organizationId },
    orderBy: { createdAt: "desc" },
    take: 50,
  });
  return rows.map((row) => ({
    queue: "open_question" as const,
    queueLabel: ATTENTION_QUEUE_LABELS.open_question,
    itemId: row.id,
    // Open questions don't carry a numeric severity; treat them as
    // medium so they out-rank low-severity drift but never out-rank
    // a high-severity peer-review escalation.
    severity: "medium" as const,
    createdAt: row.createdAt,
    preview: row.summary || row.unresolvedReason || "Open question",
    link: `/open-questions#${row.id}`,
  }));
}

async function fetchCitationVerdictItems(
  tenant: TenantContext,
): Promise<AttentionItem[]> {
  const rows = await db.citationVerdict.findMany({
    where: {
      organizationId: tenant.organizationId,
      relationHolds: { in: ["CONTRADICTS", "AMBIGUOUS"] },
      overriddenById: null,
    },
    orderBy: { computedAt: "desc" },
    take: 50,
  });
  return rows.map((row) => ({
    queue: "citation_verdict" as const,
    queueLabel: ATTENTION_QUEUE_LABELS.citation_verdict,
    itemId: row.id,
    severity:
      row.relationHolds === "CONTRADICTS"
        ? ("high" as const)
        : ("medium" as const),
    createdAt: row.computedAt,
    preview:
      `Citation ${row.citationKind} ${row.citationId.slice(0, 12)} → ${row.relationHolds} ` +
      `(${row.relation}) on ${row.sourceId}`,
    link: `/source-triage#verdict-${row.id}`,
  }));
}

// ── Severity helpers ───────────────────────────────────────────────────

function driftScoreSeverity(score: number): AttentionSeverity {
  if (score >= 0.7) return "high";
  if (score >= 0.4) return "medium";
  return "low";
}

function methodSeverityToAttention(severity: string | null): AttentionSeverity {
  if (severity === "escalate") return "high";
  if (severity === "warn") return "medium";
  return "low";
}

function scalarSeverity(value: number): AttentionSeverity {
  if (value >= 0.7) return "high";
  if (value >= 0.4) return "medium";
  return "low";
}

function sourceTriageSeverity(
  status: string,
  isRetraction: boolean,
): AttentionSeverity {
  if (status === "RETRACTED") return "high";
  if (status === "DISPUTED" || status === "EXPIRED") return "medium";
  return isRetraction ? "medium" : "medium";
}

function truncate(value: string, max: number): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

// ── Action ledger I/O ──────────────────────────────────────────────────

export async function loadAttentionActions(
  tenant: TenantContext,
): Promise<AttentionItemActionRow[]> {
  try {
    const rows = await db.attentionAction.findMany({
      where: {
        organizationId: tenant.organizationId,
        founderId: tenant.founderId,
      },
      orderBy: { createdAt: "asc" },
    });
    return rows
      .filter((row): row is typeof row & { queue: AttentionQueueId } =>
        (ATTENTION_QUEUES as readonly string[]).includes(row.queue),
      )
      .map((row) => ({
        queue: row.queue as AttentionQueueId,
        itemId: row.itemId,
        action: row.action as "snooze" | "dismiss" | "unsnooze",
        snoozedUntil: row.snoozedUntil,
        reason: row.reason,
        createdAt: row.createdAt,
      }));
  } catch (err) {
    console.error("[attention] action load failed:", err);
    return [];
  }
}

/**
 * Aggregated summary of dismissals per queue. A high rate of
 * dismissals on a particular queue is itself a tuning signal — the
 * dashboard surfaces this as a hint that the queue is producing too
 * much noise.
 */
export async function dismissalRateByQueue(
  tenant: TenantContext,
  windowDays = 30,
): Promise<Array<{ queue: AttentionQueueId; count: number }>> {
  const since = new Date(Date.now() - windowDays * 24 * 60 * 60 * 1000);
  try {
    const rows = await db.attentionAction.findMany({
      where: {
        organizationId: tenant.organizationId,
        action: "dismiss",
        createdAt: { gte: since },
      },
      select: { queue: true },
    });
    const counts = new Map<AttentionQueueId, number>();
    for (const row of rows) {
      if ((ATTENTION_QUEUES as readonly string[]).includes(row.queue)) {
        const queue = row.queue as AttentionQueueId;
        counts.set(queue, (counts.get(queue) ?? 0) + 1);
      }
    }
    return Array.from(counts.entries())
      .map(([queue, count]) => ({ queue, count }))
      .sort((a, b) => b.count - a.count);
  } catch (err) {
    console.error("[attention] dismissal rate query failed:", err);
    return [];
  }
}

// ── Top-level gather ───────────────────────────────────────────────────

type QueueFetcher = (tenant: TenantContext) => Promise<AttentionItem[]>;

const QUEUE_FETCHERS: QueueFetcher[] = [
  fetchDriftItems,
  fetchCalibrationBreachItems,
  fetchPeerReviewItems,
  fetchSourceTriageItems,
  fetchResponseTriageItems,
  fetchOpenQuestionItems,
  fetchCitationVerdictItems,
];

export async function gatherAttentionItems(
  tenant: TenantContext,
): Promise<AttentionItem[]> {
  const results = await Promise.all(
    QUEUE_FETCHERS.map((fetcher) =>
      fetcher(tenant).catch((err) => {
        console.error(`[attention] queue fetcher ${fetcher.name} failed:`, err);
        return [] as AttentionItem[];
      }),
    ),
  );
  return results.flat();
}

export type AttentionListing = {
  items: AttentionItem[];
  dismissalRates: Array<{ queue: AttentionQueueId; count: number }>;
  generatedAt: Date;
};

/**
 * One-shot: gather raw items from every queue, drop ones the founder
 * has dismissed or actively snoozed, rank what's left.
 */
export async function listAttentionForFounder(
  tenant: TenantContext,
  now: Date = new Date(),
): Promise<AttentionListing> {
  const [items, actions, dismissalRates] = await Promise.all([
    gatherAttentionItems(tenant),
    loadAttentionActions(tenant),
    dismissalRateByQueue(tenant),
  ]);
  const surviving = applyFounderActions(items, actions, now);
  return {
    items: rankAttentionItems(surviving, now),
    dismissalRates,
    generatedAt: now,
  };
}
