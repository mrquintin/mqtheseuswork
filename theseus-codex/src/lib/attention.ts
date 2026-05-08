import { db } from "@/lib/db";
import {
  applyFounderActions,
  ATTENTION_QUEUE_LABELS,
  ATTENTION_QUEUES,
  rankAttentionItems,
  type AttentionItem,
  type AttentionItemActionRow,
  type AttentionQueueId,
  type AttentionSeverity,
} from "@/lib/attentionShared";
import type { TenantContext } from "@/lib/tenant";
export {
  applyFounderActions,
  ATTENTION_QUEUE_LABELS,
  ATTENTION_QUEUES,
  DISMISS_REASON_DEFERRED,
  MAX_SNOOZE_DAYS,
  MAX_SNOOZE_MS,
  rankAttentionItems,
  resolveSnoozeRequest,
  severityRank,
  type AttentionItem,
  type AttentionItemAction,
  type AttentionItemActionRow,
  type AttentionQueueId,
  type AttentionSeverity,
} from "@/lib/attentionShared";

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
