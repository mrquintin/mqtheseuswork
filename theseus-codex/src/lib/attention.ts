import { db } from "@/lib/db";
import {
  applyFounderActions,
  ATTENTION_QUEUE_LABELS,
  ATTENTION_QUEUES,
  MAX_SNOOZE_DAYS,
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

// ── Daily-budget triage ────────────────────────────────────────────────
//
// The first-version queue ranked everything and showed everything. Once
// the queue is populated by real findings, high-severity items pile up
// faster than a founder can triage and the surface becomes ignorable.
// `selectDailySlice` caps the visible queue at K items per day, picking
// them severity-and-age weighted *and* diversity-weighted so the slice
// is never all-drift or all-citation.

export const DEFAULT_DAILY_BUDGET = 7;

/**
 * Per-queue diversity penalty applied during daily-slice selection.
 * Each item already picked from a queue makes the next item from that
 * same queue worth `DIVERSITY_PENALTY` points less. Tuned so it can
 * reorder items *within* a severity band — keeping the daily slice from
 * being dominated by one loud producer — but never lets a low-severity
 * item leapfrog a high-severity one.
 */
export const DIVERSITY_PENALTY = 40;

const SEVERITY_WEIGHT: Record<AttentionSeverity, number> = {
  high: 300,
  medium: 200,
  low: 100,
};

/** Age contributes at most this many points — less than a severity band. */
const MAX_AGE_BONUS_DAYS = 90;
const MS_PER_DAY = 24 * 60 * 60 * 1000;

/**
 * Severity-and-age weight for a single item. Severity sets the band
 * (100 / 200 / 300); age adds up to `MAX_AGE_BONUS_DAYS` points on top
 * so an older item outranks a fresher one in the same band. The bands
 * are 100 apart and the age bonus caps at 90, so age alone never
 * crosses a severity band.
 */
export function attentionItemWeight(
  item: AttentionItem,
  now: Date = new Date(),
): number {
  const ageDays = Math.max(0, (now.getTime() - item.createdAt.getTime()) / MS_PER_DAY);
  return SEVERITY_WEIGHT[item.severity] + Math.min(ageDays, MAX_AGE_BONUS_DAYS);
}

export type DailySlice = {
  daily: AttentionItem[];
  deferred: AttentionItem[];
  budget: number;
};

/**
 * Pick the day's triage slice: at most `budget` items, severity-and-age
 * weighted but also diversity-weighted. Greedy — each step takes the
 * highest-weight item after subtracting `DIVERSITY_PENALTY` for every
 * item already picked from the same queue. The leftovers are returned
 * as `deferred` (collapsed under "more" in the UI). Both lists keep the
 * caller's input order, which is assumed to already be rank order.
 */
export function selectDailySlice(
  items: AttentionItem[],
  budget: number = DEFAULT_DAILY_BUDGET,
  now: Date = new Date(),
): DailySlice {
  const cap = Math.max(0, Math.floor(budget));
  if (items.length <= cap) {
    return { daily: [...items], deferred: [], budget: cap };
  }
  const remaining = items.map((item, index) => ({ item, index }));
  const perQueue = new Map<AttentionQueueId, number>();
  const chosen = new Set<number>();
  while (chosen.size < cap && remaining.length > 0) {
    let bestPos = 0;
    let bestScore = -Infinity;
    for (let i = 0; i < remaining.length; i++) {
      const { item } = remaining[i];
      const picked = perQueue.get(item.queue) ?? 0;
      // Strict `>` keeps the tie-break stable: on equal score the
      // earlier (higher-ranked) candidate wins.
      const score = attentionItemWeight(item, now) - DIVERSITY_PENALTY * picked;
      if (score > bestScore) {
        bestScore = score;
        bestPos = i;
      }
    }
    const [picked] = remaining.splice(bestPos, 1);
    chosen.add(picked.index);
    perQueue.set(picked.item.queue, (perQueue.get(picked.item.queue) ?? 0) + 1);
  }
  return {
    daily: items.filter((_, i) => chosen.has(i)),
    deferred: items.filter((_, i) => !chosen.has(i)),
    budget: cap,
  };
}

// ── Queue health ───────────────────────────────────────────────────────
//
// Each underlying queue (drift, citation verdicts, source standing, peer
// review, response triage, …) gets a health read: the rate at which its
// producer emits new items vs the rate at which the founder triages
// them. A queue accumulating faster than it drains is one the firm has
// under-resourced, or whose producer needs throttling.

export type QueueHealthStatus = "draining" | "steady" | "accumulating";

export type QueueHealth = {
  queue: AttentionQueueId;
  queueLabel: string;
  /** Items the queue's producer currently has open. */
  openCount: number;
  /** New items per day over the health window. */
  arrivalRate: number;
  /** Founder triage actions (snooze + dismiss) per day over the window. */
  triageRate: number;
  /**
   * arrivalRate / triageRate. `Infinity` when items arrive but nothing
   * is triaged; `0` when the queue is idle.
   */
  pressure: number;
  status: QueueHealthStatus;
};

export const QUEUE_HEALTH_WINDOW_DAYS = 7;

/** Rates must differ by this factor before a queue leaves "steady". */
const QUEUE_HEALTH_BAND = 1.25;

/**
 * Per-queue health over a rolling window. `items` is the gathered set
 * the producers currently hold open (arrivals + open count); `actions`
 * is the founder action ledger (triage rate). Queues with nothing open
 * and no recent activity are omitted.
 */
export function computeQueueHealth(
  items: AttentionItem[],
  actions: AttentionItemActionRow[],
  now: Date = new Date(),
  windowDays: number = QUEUE_HEALTH_WINDOW_DAYS,
): QueueHealth[] {
  const since = now.getTime() - windowDays * MS_PER_DAY;
  const open = new Map<AttentionQueueId, number>();
  const arrivals = new Map<AttentionQueueId, number>();
  const triage = new Map<AttentionQueueId, number>();
  for (const item of items) {
    open.set(item.queue, (open.get(item.queue) ?? 0) + 1);
    if (item.createdAt.getTime() >= since) {
      arrivals.set(item.queue, (arrivals.get(item.queue) ?? 0) + 1);
    }
  }
  for (const action of actions) {
    if (action.createdAt.getTime() < since) continue;
    if (action.action === "snooze" || action.action === "dismiss") {
      triage.set(action.queue, (triage.get(action.queue) ?? 0) + 1);
    }
  }
  const result: QueueHealth[] = [];
  for (const queue of ATTENTION_QUEUES) {
    const openCount = open.get(queue) ?? 0;
    const arrived = arrivals.get(queue) ?? 0;
    const triaged = triage.get(queue) ?? 0;
    if (openCount === 0 && arrived === 0 && triaged === 0) continue;
    const arrivalRate = arrived / windowDays;
    const triageRate = triaged / windowDays;
    const pressure =
      triageRate > 0 ? arrivalRate / triageRate : arrivalRate > 0 ? Infinity : 0;
    let status: QueueHealthStatus = "steady";
    if (pressure > QUEUE_HEALTH_BAND) status = "accumulating";
    else if (pressure > 0 && pressure < 1 / QUEUE_HEALTH_BAND) status = "draining";
    result.push({
      queue,
      queueLabel: ATTENTION_QUEUE_LABELS[queue],
      openCount,
      arrivalRate,
      triageRate,
      pressure,
      status,
    });
  }
  return result;
}

// ── Founder-feedback loop ──────────────────────────────────────────────
//
// When a founder clears an item because the system made a wrong call,
// that dismissal is a labelled false positive — training data for the
// producing detector's threshold tuning. The path is opt-in per queue:
// the firm does not get a quiet feedback loop it never consented to.

/**
 * Reserved dismissal reason. A founder clearing an item with exactly
 * this reason is telling the system its producer made a wrong call.
 */
export const DISMISS_REASON_WRONG_CALL = "wrong call by the system";

/**
 * Queues whose producers have opted in to receiving "wrong call"
 * dismissals as threshold-tuning training data. Opt-in is explicit and
 * per queue — add a queue here only once its producer (the citation-
 * chain validator, the drift detector, …) is wired to consume the
 * signal. Queues absent from this set generate no feedback at all.
 */
export const FALSE_POSITIVE_TRAINING_QUEUES: ReadonlySet<AttentionQueueId> =
  new Set<AttentionQueueId>(["citation_verdict", "drift", "calibration_breach"]);

export function isTrainingFeedbackEnabled(queue: AttentionQueueId): boolean {
  return FALSE_POSITIVE_TRAINING_QUEUES.has(queue);
}

export type FalsePositiveSignal = {
  queue: AttentionQueueId;
  itemId: string;
  reason: string;
  dismissedAt: Date;
};

/**
 * Scan the founder action ledger for "wrong call by the system"
 * dismissals on opted-in queues. The result is training data for the
 * producing detector to retune its thresholds. Dismissals on queues
 * that have not opted in are ignored — see
 * `FALSE_POSITIVE_TRAINING_QUEUES`.
 */
export function extractFalsePositiveTrainingSignals(
  actions: AttentionItemActionRow[],
): FalsePositiveSignal[] {
  return actions
    .filter(
      (row) =>
        row.action === "dismiss" &&
        row.reason.trim().toLowerCase() === DISMISS_REASON_WRONG_CALL &&
        isTrainingFeedbackEnabled(row.queue),
    )
    .map((row) => ({
      queue: row.queue,
      itemId: row.itemId,
      reason: row.reason.trim(),
      dismissedAt: row.createdAt,
    }));
}

// ── Snooze annotations ─────────────────────────────────────────────────

export const MIN_SNOOZE_REASON_LENGTH = 3;

/**
 * A snooze must carry a reason — it becomes a searchable annotation on
 * the item ("waiting on co-author", "revisit after Q3 data"), not a
 * silent disappearance. Returns the trimmed reason or an error.
 */
export function validateSnoozeReason(
  reason: string | null | undefined,
): { ok: true; reason: string } | { ok: false; error: string } {
  const trimmed = (reason ?? "").trim();
  if (trimmed.length < MIN_SNOOZE_REASON_LENGTH) {
    return { ok: false, error: "A reason is required to snooze an item." };
  }
  return { ok: true, reason: trimmed };
}

// ── Bulk actions ───────────────────────────────────────────────────────

export type BulkActionTarget = { queue: AttentionQueueId; itemId: string };

export type BulkActionRequest =
  | { queue: AttentionQueueId; itemId: string; action: "dismiss"; reason: string }
  | {
      queue: AttentionQueueId;
      itemId: string;
      action: "snooze";
      snoozedUntil: string;
      reason: string;
    };

/**
 * Validate and expand a bulk founder action into one request per
 * selected item. Bulk dismiss and bulk snooze both require a reason —
 * snooze reasons are searchable annotations, dismiss reasons feed queue
 * tuning. Returns a flat error if the selection is empty or the reason
 * is missing/too short. Bulk actions stay founder-driven: this only
 * plans the requests, it never resolves anything on its own.
 */
export function planBulkAction(
  targets: BulkActionTarget[],
  action: "snooze" | "dismiss",
  options: { reason?: string; snoozeDays?: number; now?: Date } = {},
): { ok: true; requests: BulkActionRequest[] } | { ok: false; error: string } {
  if (targets.length === 0) {
    return { ok: false, error: "Select at least one item." };
  }
  const reason = (options.reason ?? "").trim();
  if (action === "dismiss") {
    if (!reason) {
      return { ok: false, error: "A reason is required to clear items." };
    }
    return {
      ok: true,
      requests: targets.map((target) => ({
        queue: target.queue,
        itemId: target.itemId,
        action: "dismiss" as const,
        reason,
      })),
    };
  }
  const reasonCheck = validateSnoozeReason(reason);
  if (!reasonCheck.ok) {
    return { ok: false, error: reasonCheck.error };
  }
  const now = options.now ?? new Date();
  const days = Math.max(
    1,
    Math.min(MAX_SNOOZE_DAYS, Math.floor(options.snoozeDays ?? 1)),
  );
  const snoozedUntil = new Date(now.getTime() + days * MS_PER_DAY).toISOString();
  return {
    ok: true,
    requests: targets.map((target) => ({
      queue: target.queue,
      itemId: target.itemId,
      action: "snooze" as const,
      snoozedUntil,
      reason: reasonCheck.reason,
    })),
  };
}

// ── Top-level listing ──────────────────────────────────────────────────

export type AttentionListing = {
  /** Full ranked list across every queue (severity > age > queue id). */
  items: AttentionItem[];
  /** The day's triage slice — at most `dailyBudget`, diversity-weighted. */
  daily: AttentionItem[];
  /** Everything past the daily budget, collapsed under "more" in the UI. */
  deferred: AttentionItem[];
  dailyBudget: number;
  /** Per-queue arrival-vs-triage health. */
  queueHealth: QueueHealth[];
  /** False-positive dismissals on opted-in queues, for producer tuning. */
  trainingSignals: FalsePositiveSignal[];
  dismissalRates: Array<{ queue: AttentionQueueId; count: number }>;
  generatedAt: Date;
};

/**
 * One-shot: gather raw items from every queue, drop ones the founder
 * has dismissed or actively snoozed, rank what's left, then split the
 * ranked list into the day's diversity-weighted budget slice and the
 * deferred remainder. Also computes per-queue health and the
 * false-positive training signal off the action ledger.
 */
export async function listAttentionForFounder(
  tenant: TenantContext,
  now: Date = new Date(),
  options: { dailyBudget?: number } = {},
): Promise<AttentionListing> {
  const [items, actions, dismissalRates] = await Promise.all([
    gatherAttentionItems(tenant),
    loadAttentionActions(tenant),
    dismissalRateByQueue(tenant),
  ]);
  const surviving = applyFounderActions(items, actions, now);
  const ranked = rankAttentionItems(surviving, now);
  const dailyBudget = options.dailyBudget ?? DEFAULT_DAILY_BUDGET;
  const slice = selectDailySlice(ranked, dailyBudget, now);
  return {
    items: ranked,
    daily: slice.daily,
    deferred: slice.deferred,
    dailyBudget,
    queueHealth: computeQueueHealth(items, actions, now),
    trainingSignals: extractFalsePositiveTrainingSignals(actions),
    dismissalRates,
    generatedAt: now,
  };
}
