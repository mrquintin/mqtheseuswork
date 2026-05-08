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
