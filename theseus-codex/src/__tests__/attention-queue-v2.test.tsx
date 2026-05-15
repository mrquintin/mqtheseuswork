import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Round 17 prompt 34 (refined) — daily-budget triage, diversity
 * weighting, bulk actions, queue health, the false-positive training
 * loop, and required snooze reasons. The first-version coverage lives
 * in `AttentionQueue.test.tsx`; this file exercises the v2 refinements.
 */

const dbMock = vi.hoisted(() => ({
  driftEvent: { findMany: vi.fn() },
  reviewItem: { findMany: vi.fn() },
  sourceTriageItem: { findMany: vi.fn() },
  responseTriage: { findMany: vi.fn() },
  openQuestion: { findMany: vi.fn() },
  citationVerdict: { findMany: vi.fn() },
  attentionAction: { findMany: vi.fn(), create: vi.fn() },
}));

vi.mock("@/lib/db", () => ({ db: dbMock }));

import {
  attentionItemWeight,
  computeQueueHealth,
  DEFAULT_DAILY_BUDGET,
  DISMISS_REASON_WRONG_CALL,
  extractFalsePositiveTrainingSignals,
  FALSE_POSITIVE_TRAINING_QUEUES,
  isTrainingFeedbackEnabled,
  listAttentionForFounder,
  planBulkAction,
  selectDailySlice,
  validateSnoozeReason,
  type AttentionItem,
  type AttentionItemActionRow,
} from "@/lib/attention";

const NOW = new Date("2026-05-14T08:00:00.000Z");
const MS_PER_DAY = 24 * 60 * 60 * 1000;

const tenant = {
  organizationId: "org-1",
  organizationSlug: "theseus-local",
  founderId: "founder-1",
  founderName: "alpha",
  founderUsername: "alpha",
  role: "founder",
} as const;

function item(
  overrides: Partial<AttentionItem> &
    Pick<AttentionItem, "queue" | "itemId" | "severity" | "createdAt">,
): AttentionItem {
  return {
    queueLabel: overrides.queue,
    preview: overrides.preview ?? "preview",
    link: overrides.link ?? `/x/${overrides.itemId}`,
    ...overrides,
  };
}

function ageDays(days: number): Date {
  return new Date(NOW.getTime() - days * MS_PER_DAY);
}

// ── A. Daily-budget triage ─────────────────────────────────────────────

describe("selectDailySlice — daily budget", () => {
  it("never returns more than the budget, and defers the rest", () => {
    const items: AttentionItem[] = Array.from({ length: 20 }, (_, i) =>
      item({
        queue: "drift",
        itemId: `d-${i}`,
        severity: "medium",
        createdAt: ageDays(i),
      }),
    );
    const slice = selectDailySlice(items, 7, NOW);
    expect(slice.daily).toHaveLength(7);
    expect(slice.deferred).toHaveLength(13);
    expect(slice.budget).toBe(7);
    // Every item is accounted for exactly once.
    const ids = new Set([
      ...slice.daily.map((r) => r.itemId),
      ...slice.deferred.map((r) => r.itemId),
    ]);
    expect(ids.size).toBe(20);
  });

  it("returns everything when the queue is under budget", () => {
    const items = [
      item({ queue: "drift", itemId: "a", severity: "high", createdAt: NOW }),
      item({ queue: "peer_review", itemId: "b", severity: "low", createdAt: NOW }),
    ];
    const slice = selectDailySlice(items, DEFAULT_DAILY_BUDGET, NOW);
    expect(slice.daily).toHaveLength(2);
    expect(slice.deferred).toHaveLength(0);
  });

  it("is diversity-weighted: one loud queue cannot fill the whole slice", () => {
    // Six old high-severity drift items would monopolise a pure
    // severity/age ranking; two fresh medium citation verdicts would
    // never make the cut.
    const items: AttentionItem[] = [
      ...Array.from({ length: 6 }, (_, i) =>
        item({
          queue: "drift",
          itemId: `drift-${i}`,
          severity: "high",
          createdAt: ageDays(10),
        }),
      ),
      item({
        queue: "citation_verdict",
        itemId: "cite-0",
        severity: "medium",
        createdAt: NOW,
      }),
      item({
        queue: "citation_verdict",
        itemId: "cite-1",
        severity: "medium",
        createdAt: NOW,
      }),
    ];
    const slice = selectDailySlice(items, 5, NOW);
    expect(slice.daily).toHaveLength(5);
    const queuesInSlice = new Set(slice.daily.map((r) => r.queue));
    expect(queuesInSlice.size).toBeGreaterThan(1);
    expect(queuesInSlice.has("citation_verdict")).toBe(true);
  });

  it("never lets the diversity penalty promote low severity over high", () => {
    const items: AttentionItem[] = [
      ...Array.from({ length: 3 }, (_, i) =>
        item({
          queue: "drift",
          itemId: `drift-${i}`,
          severity: "high",
          createdAt: ageDays(5),
        }),
      ),
      item({
        queue: "citation_verdict",
        itemId: "cite-low",
        severity: "low",
        createdAt: NOW,
      }),
    ];
    const slice = selectDailySlice(items, 3, NOW);
    expect(slice.daily.every((r) => r.severity === "high")).toBe(true);
    expect(slice.deferred.map((r) => r.itemId)).toEqual(["cite-low"]);
  });

  it("weights an older item above a fresher one in the same severity band", () => {
    const old = item({
      queue: "drift",
      itemId: "old",
      severity: "high",
      createdAt: ageDays(20),
    });
    const fresh = item({
      queue: "drift",
      itemId: "fresh",
      severity: "high",
      createdAt: NOW,
    });
    expect(attentionItemWeight(old, NOW)).toBeGreaterThan(
      attentionItemWeight(fresh, NOW),
    );
    // ...but a high-severity fresh item still outweighs a low-severity
    // ancient one — severity bands are never crossed by age alone.
    const ancientLow = item({
      queue: "drift",
      itemId: "ancient-low",
      severity: "low",
      createdAt: ageDays(365),
    });
    expect(attentionItemWeight(fresh, NOW)).toBeGreaterThan(
      attentionItemWeight(ancientLow, NOW),
    );
  });
});

// ── B. Bulk actions ────────────────────────────────────────────────────

describe("planBulkAction", () => {
  const targets = [
    { queue: "drift" as const, itemId: "d-1" },
    { queue: "peer_review" as const, itemId: "p-1" },
  ];

  it("rejects an empty selection", () => {
    const result = planBulkAction([], "dismiss", { reason: "resolved" });
    expect(result.ok).toBe(false);
  });

  it("requires a reason for bulk dismiss", () => {
    const result = planBulkAction(targets, "dismiss", { reason: "  " });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toMatch(/reason/i);
  });

  it("requires a reason for bulk snooze", () => {
    const result = planBulkAction(targets, "snooze", { snoozeDays: 3 });
    expect(result.ok).toBe(false);
  });

  it("expands a valid bulk dismiss into one request per target", () => {
    const result = planBulkAction(targets, "dismiss", {
      reason: "duplicate finding",
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.requests).toHaveLength(2);
      expect(result.requests.every((r) => r.action === "dismiss")).toBe(true);
      expect(result.requests.every((r) => r.reason === "duplicate finding")).toBe(
        true,
      );
      expect(result.requests.map((r) => r.itemId)).toEqual(["d-1", "p-1"]);
    }
  });

  it("expands a valid bulk snooze with a clamped duration and reason", () => {
    const result = planBulkAction(targets, "snooze", {
      reason: "waiting on co-author",
      snoozeDays: 999, // clamped to MAX_SNOOZE_DAYS
      now: NOW,
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.requests).toHaveLength(2);
      for (const request of result.requests) {
        expect(request.action).toBe("snooze");
        if (request.action === "snooze") {
          expect(request.reason).toBe("waiting on co-author");
          const until = new Date(request.snoozedUntil).getTime();
          // 14-day cap, not 999.
          expect(until - NOW.getTime()).toBe(14 * MS_PER_DAY);
        }
      }
    }
  });
});

// ── C. Queue health ────────────────────────────────────────────────────

describe("computeQueueHealth", () => {
  it("flags a queue arriving faster than it is triaged as accumulating", () => {
    const items: AttentionItem[] = Array.from({ length: 10 }, (_, i) =>
      item({
        queue: "drift",
        itemId: `d-${i}`,
        severity: "medium",
        createdAt: ageDays(i % 7),
      }),
    );
    const health = computeQueueHealth(items, [], NOW);
    const drift = health.find((h) => h.queue === "drift");
    expect(drift).toBeDefined();
    expect(drift?.status).toBe("accumulating");
    expect(drift?.openCount).toBe(10);
    expect(drift?.triageRate).toBe(0);
    expect(drift?.pressure).toBe(Infinity);
  });

  it("flags a queue triaged faster than it arrives as draining", () => {
    const items: AttentionItem[] = [
      item({
        queue: "peer_review",
        itemId: "p-1",
        severity: "high",
        createdAt: ageDays(1),
      }),
    ];
    const actions: AttentionItemActionRow[] = Array.from(
      { length: 8 },
      (_, i) => ({
        queue: "peer_review",
        itemId: `cleared-${i}`,
        action: "dismiss",
        snoozedUntil: null,
        reason: "resolved",
        createdAt: ageDays(i % 7),
      }),
    );
    const health = computeQueueHealth(items, actions, NOW);
    const peer = health.find((h) => h.queue === "peer_review");
    expect(peer?.status).toBe("draining");
  });

  it("calls a queue holding pace steady, and omits idle queues", () => {
    const items: AttentionItem[] = Array.from({ length: 4 }, (_, i) =>
      item({
        queue: "open_question",
        itemId: `q-${i}`,
        severity: "medium",
        createdAt: ageDays(i),
      }),
    );
    const actions: AttentionItemActionRow[] = Array.from(
      { length: 4 },
      (_, i) => ({
        queue: "open_question",
        itemId: `done-${i}`,
        action: "snooze",
        snoozedUntil: ageDays(-1),
        reason: "later",
        createdAt: ageDays(i),
      }),
    );
    const health = computeQueueHealth(items, actions, NOW);
    const oq = health.find((h) => h.queue === "open_question");
    expect(oq?.status).toBe("steady");
    expect(oq?.pressure).toBe(1);
    // Queues with no items and no activity are not reported at all.
    expect(health.some((h) => h.queue === "calibration_breach")).toBe(false);
  });
});

// ── D. Founder-feedback loop ───────────────────────────────────────────

describe("extractFalsePositiveTrainingSignals", () => {
  it("collects 'wrong call' dismissals only on opted-in queues", () => {
    // Sanity: the opt-in set is explicit and non-empty.
    expect(isTrainingFeedbackEnabled("citation_verdict")).toBe(true);
    expect(FALSE_POSITIVE_TRAINING_QUEUES.has("citation_verdict")).toBe(true);

    const optedOutQueue = [...["open_question", "peer_review"] as const].find(
      (q) => !isTrainingFeedbackEnabled(q),
    );
    expect(optedOutQueue).toBeDefined();

    const actions: AttentionItemActionRow[] = [
      {
        queue: "citation_verdict",
        itemId: "good-signal",
        action: "dismiss",
        snoozedUntil: null,
        reason: DISMISS_REASON_WRONG_CALL,
        createdAt: NOW,
      },
      {
        queue: "drift",
        itemId: "case-insensitive",
        action: "dismiss",
        snoozedUntil: null,
        reason: "WRONG CALL BY THE SYSTEM",
        createdAt: NOW,
      },
      {
        // Opted-out queue — never fed back, even with the exact reason.
        queue: optedOutQueue!,
        itemId: "no-consent",
        action: "dismiss",
        snoozedUntil: null,
        reason: DISMISS_REASON_WRONG_CALL,
        createdAt: NOW,
      },
      {
        // Right queue, ordinary dismissal reason — not a training signal.
        queue: "drift",
        itemId: "ordinary",
        action: "dismiss",
        snoozedUntil: null,
        reason: "duplicate",
        createdAt: NOW,
      },
      {
        // A snooze is not a dismissal.
        queue: "drift",
        itemId: "snoozed",
        action: "snooze",
        snoozedUntil: new Date(NOW.getTime() + MS_PER_DAY),
        reason: DISMISS_REASON_WRONG_CALL,
        createdAt: NOW,
      },
    ];

    const signals = extractFalsePositiveTrainingSignals(actions);
    expect(signals.map((s) => s.itemId).sort()).toEqual([
      "case-insensitive",
      "good-signal",
    ]);
    expect(signals.every((s) => isTrainingFeedbackEnabled(s.queue))).toBe(true);
  });
});

// ── E. Snooze reasons required ─────────────────────────────────────────

describe("validateSnoozeReason", () => {
  it("rejects empty or too-short reasons", () => {
    expect(validateSnoozeReason("").ok).toBe(false);
    expect(validateSnoozeReason("   ").ok).toBe(false);
    expect(validateSnoozeReason("ab").ok).toBe(false);
    expect(validateSnoozeReason(null).ok).toBe(false);
    expect(validateSnoozeReason(undefined).ok).toBe(false);
  });

  it("accepts and trims a real reason", () => {
    const result = validateSnoozeReason("  revisit after Q3 data  ");
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.reason).toBe("revisit after Q3 data");
  });
});

// ── F. Integration — synthetic mixed queue ─────────────────────────────

describe("listAttentionForFounder — daily budget + queue health", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    dbMock.driftEvent.findMany.mockImplementation(
      async ({ where }: { where: Record<string, unknown> }) => {
        if ((where as { targetKind?: string }).targetKind === "method") {
          return [
            {
              id: "method-1",
              observedAt: ageDays(2),
              severity: "escalate",
              driftScore: 0.9,
              naturalLanguageSummary: "method drift escalated",
              notes: "",
              targetKind: "method",
              targetId: "method:six_layer@1",
              methodName: "six_layer",
              methodVersion: "1",
            },
          ];
        }
        // Five high-severity principle drift items — a single loud queue.
        return Array.from({ length: 5 }, (_, i) => ({
          id: `drift-${i}`,
          observedAt: ageDays(3 + i),
          severity: null,
          driftScore: 0.85,
          naturalLanguageSummary: `principle drift ${i}`,
          notes: "",
          targetKind: "principle",
          targetId: `principle-${i}`,
        }));
      },
    );
    dbMock.reviewItem.findMany.mockResolvedValue([
      {
        id: "review-1",
        createdAt: ageDays(1),
        severity: 0.95,
        reason: "peer-review escalation",
      },
    ]);
    dbMock.sourceTriageItem.findMany.mockResolvedValue([
      {
        id: "triage-1",
        trigger: "citation",
        sourceId: "doi:1",
        conclusionId: "concl-1",
        status: "DISPUTED",
        createdAt: ageDays(4),
      },
    ]);
    dbMock.responseTriage.findMany.mockResolvedValue([]);
    dbMock.openQuestion.findMany.mockResolvedValue([]);
    dbMock.citationVerdict.findMany.mockResolvedValue([
      {
        id: "verdict-1",
        relationHolds: "CONTRADICTS",
        relation: "supports",
        citationKind: "inline",
        citationId: "cite-abc-123",
        sourceId: "src-1",
        computedAt: ageDays(1),
      },
    ]);
    dbMock.attentionAction.findMany.mockResolvedValue([]);
  });

  it("honors the daily budget and keeps the slice diverse", async () => {
    const listing = await listAttentionForFounder(tenant, NOW, {
      dailyBudget: 4,
    });
    // 5 drift + 1 method + 1 review + 1 triage + 1 verdict = 9 total.
    expect(listing.items).toHaveLength(9);
    expect(listing.dailyBudget).toBe(4);
    expect(listing.daily).toHaveLength(4);
    expect(listing.deferred).toHaveLength(5);
    // The drift queue alone could fill the slice on a pure severity/age
    // ranking; diversity weighting must pull in at least one other queue.
    const queuesInSlice = new Set(listing.daily.map((r) => r.queue));
    expect(queuesInSlice.size).toBeGreaterThan(1);
  });

  it("defaults the budget when none is supplied", async () => {
    const listing = await listAttentionForFounder(tenant, NOW);
    expect(listing.dailyBudget).toBe(DEFAULT_DAILY_BUDGET);
    expect(listing.daily.length).toBeLessThanOrEqual(DEFAULT_DAILY_BUDGET);
  });

  it("reports per-queue health for queues with open items", async () => {
    const listing = await listAttentionForFounder(tenant, NOW);
    expect(listing.queueHealth.length).toBeGreaterThan(0);
    const drift = listing.queueHealth.find((h) => h.queue === "drift");
    expect(drift).toBeDefined();
    // Five drift items, no triage actions in the window → accumulating.
    expect(drift?.status).toBe("accumulating");
    expect(drift?.openCount).toBe(5);
  });
});
