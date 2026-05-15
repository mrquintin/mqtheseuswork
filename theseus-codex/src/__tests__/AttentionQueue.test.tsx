import { beforeEach, describe, expect, it, vi } from "vitest";

const dbMock = vi.hoisted(() => ({
  driftEvent: { findMany: vi.fn() },
  reviewItem: { findMany: vi.fn() },
  sourceTriageItem: { findMany: vi.fn() },
  responseTriage: { findMany: vi.fn() },
  openQuestion: { findMany: vi.fn() },
  citationVerdict: { findMany: vi.fn() },
  attentionAction: {
    findMany: vi.fn(),
    create: vi.fn(),
  },
  founder: { findMany: vi.fn() },
}));

vi.mock("@/lib/db", () => ({ db: dbMock }));

import {
  applyFounderActions,
  ATTENTION_QUEUES,
  DISMISS_REASON_DEFERRED,
  listAttentionForFounder,
  loadAttentionActions,
  MAX_SNOOZE_DAYS,
  rankAttentionItems,
  resolveSnoozeRequest,
  type AttentionItem,
  type AttentionItemActionRow,
} from "@/lib/attention";

import {
  buildDigestEmail,
  buildDigestPayload,
} from "@/lib/dailyDigestEmail";

import { POST } from "@/app/api/founder/attention/route";

vi.mock("@/lib/tenant", () => ({
  requireTenantContext: vi.fn(),
}));

import { requireTenantContext } from "@/lib/tenant";

const tenant = {
  organizationId: "org-1",
  organizationSlug: "theseus-local",
  founderId: "founder-1",
  founderName: "alpha",
  founderUsername: "alpha",
  role: "founder",
};

const NOW = new Date("2026-05-08T08:00:00.000Z");
const MS_PER_DAY = 24 * 60 * 60 * 1000;

function item(
  overrides: Partial<AttentionItem> & Pick<AttentionItem, "queue" | "itemId" | "severity" | "createdAt">,
): AttentionItem {
  return {
    queueLabel: overrides.queue,
    preview: overrides.preview ?? "preview",
    link: overrides.link ?? `/x/${overrides.itemId}`,
    ...overrides,
  };
}

describe("attention queue ranking", () => {
  it("sorts by severity descending, then by age descending within severity", () => {
    const fresh = NOW;
    const oneDay = new Date(NOW.getTime() - 1 * MS_PER_DAY);
    const sevenDays = new Date(NOW.getTime() - 7 * MS_PER_DAY);
    const thirtyDays = new Date(NOW.getTime() - 30 * MS_PER_DAY);
    const items: AttentionItem[] = [
      item({ queue: "drift", itemId: "fresh-high", severity: "high", createdAt: fresh }),
      item({ queue: "drift", itemId: "old-low", severity: "low", createdAt: thirtyDays }),
      item({ queue: "peer_review", itemId: "old-high", severity: "high", createdAt: sevenDays }),
      item({ queue: "open_question", itemId: "med-1d", severity: "medium", createdAt: oneDay }),
      item({ queue: "drift", itemId: "med-7d", severity: "medium", createdAt: sevenDays }),
    ];

    const ranked = rankAttentionItems(items, NOW);
    expect(ranked.map((row) => row.itemId)).toEqual([
      "old-high", // high severity, 7 days
      "fresh-high", // high severity, fresh
      "med-7d", // medium severity, 7 days
      "med-1d", // medium severity, 1 day
      "old-low", // low severity, 30 days
    ]);
  });

  it("never lets age outrank severity", () => {
    const items: AttentionItem[] = [
      item({
        queue: "drift",
        itemId: "ancient-low",
        severity: "low",
        createdAt: new Date(NOW.getTime() - 365 * MS_PER_DAY),
      }),
      item({
        queue: "drift",
        itemId: "fresh-high",
        severity: "high",
        createdAt: NOW,
      }),
    ];
    const ranked = rankAttentionItems(items, NOW);
    expect(ranked[0].itemId).toBe("fresh-high");
  });
});

describe("applyFounderActions", () => {
  const items: AttentionItem[] = [
    item({ queue: "drift", itemId: "a", severity: "high", createdAt: NOW }),
    item({ queue: "drift", itemId: "b", severity: "high", createdAt: NOW }),
    item({ queue: "peer_review", itemId: "c", severity: "medium", createdAt: NOW }),
  ];

  it("drops dismissed items", () => {
    const actions: AttentionItemActionRow[] = [
      {
        queue: "drift",
        itemId: "a",
        action: "dismiss",
        snoozedUntil: null,
        reason: "noise",
        createdAt: new Date(NOW.getTime() - 1000),
      },
    ];
    const out = applyFounderActions(items, actions, NOW);
    expect(out.map((row) => row.itemId)).toEqual(["b", "c"]);
  });

  it("hides items with active snooze and resurfaces expired snoozes", () => {
    const actions: AttentionItemActionRow[] = [
      {
        queue: "drift",
        itemId: "a",
        action: "snooze",
        snoozedUntil: new Date(NOW.getTime() + MS_PER_DAY),
        reason: "",
        createdAt: new Date(NOW.getTime() - 1000),
      },
      {
        queue: "drift",
        itemId: "b",
        action: "snooze",
        snoozedUntil: new Date(NOW.getTime() - 1000),
        reason: "",
        createdAt: new Date(NOW.getTime() - 2 * MS_PER_DAY),
      },
    ];
    const out = applyFounderActions(items, actions, NOW);
    expect(out.map((row) => row.itemId)).toEqual(["b", "c"]);
  });

  it("uses the latest action when several apply to the same item", () => {
    const actions: AttentionItemActionRow[] = [
      {
        queue: "drift",
        itemId: "a",
        action: "snooze",
        snoozedUntil: new Date(NOW.getTime() + MS_PER_DAY),
        reason: "",
        createdAt: new Date(NOW.getTime() - 2 * MS_PER_DAY),
      },
      {
        queue: "drift",
        itemId: "a",
        action: "unsnooze",
        snoozedUntil: null,
        reason: "",
        createdAt: new Date(NOW.getTime() - 60_000),
      },
    ];
    const out = applyFounderActions(items, actions, NOW);
    expect(out.map((row) => row.itemId)).toContain("a");
  });
});

describe("resolveSnoozeRequest", () => {
  it("clamps long snoozes by rewriting them as dismissals", () => {
    const tooLong = new Date(NOW.getTime() + (MAX_SNOOZE_DAYS + 1) * MS_PER_DAY);
    const result = resolveSnoozeRequest(tooLong, NOW);
    expect(result.kind).toBe("dismiss");
    if (result.kind === "dismiss") {
      expect(result.reason).toBe(DISMISS_REASON_DEFERRED);
    }
  });

  it("accepts a snooze inside the cap", () => {
    const fine = new Date(NOW.getTime() + 5 * MS_PER_DAY);
    const result = resolveSnoozeRequest(fine, NOW);
    expect(result.kind).toBe("snooze");
    if (result.kind === "snooze") {
      expect(result.snoozedUntil).toEqual(fine);
    }
  });
});

describe("listAttentionForFounder — synthetic queue mix", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    dbMock.driftEvent.findMany.mockImplementation(async ({ where }: { where: Record<string, unknown> }) => {
      // Two calls: one for principle drift, one for method drift.
      if ((where as { targetKind?: string }).targetKind === "method") {
        return [
          {
            id: "method-1",
            observedAt: new Date(NOW.getTime() - 3 * MS_PER_DAY),
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
      return [
        {
          id: "drift-old-high",
          observedAt: new Date(NOW.getTime() - 9 * MS_PER_DAY),
          severity: null,
          driftScore: 0.85,
          naturalLanguageSummary: "principle drift, severe",
          notes: "",
          targetKind: "principle",
          targetId: "principle-1",
        },
        {
          id: "drift-fresh-low",
          observedAt: new Date(NOW.getTime() - 1 * MS_PER_DAY),
          severity: null,
          driftScore: 0.2,
          naturalLanguageSummary: "principle drift, mild",
          notes: "",
          targetKind: "principle",
          targetId: "principle-2",
        },
      ];
    });
    dbMock.reviewItem.findMany.mockResolvedValue([
      {
        id: "review-fresh-high",
        createdAt: new Date(NOW.getTime() - 60_000),
        severity: 0.95,
        reason: "fresh review escalation",
      },
    ]);
    dbMock.sourceTriageItem.findMany.mockResolvedValue([
      {
        id: "triage-1",
        trigger: "standing",
        sourceId: "doi:1",
        conclusionId: "concl-1",
        status: "RETRACTED",
        createdAt: new Date(NOW.getTime() - 14 * MS_PER_DAY),
      },
    ]);
    dbMock.responseTriage.findMany.mockResolvedValue([]);
    dbMock.openQuestion.findMany.mockResolvedValue([]);
    dbMock.citationVerdict.findMany.mockResolvedValue([]);
    dbMock.attentionAction.findMany.mockResolvedValue([]);
  });

  it("ranks high severity items by age, then medium, then low", async () => {
    const listing = await listAttentionForFounder(tenant, NOW);
    const ids = listing.items.map((row) => row.itemId);
    expect(ids).toEqual([
      "triage-1", // high, 14 days
      "drift-old-high", // high, 9 days
      "method-1", // high, 3 days
      "review-fresh-high", // high, fresh
      "drift-fresh-low", // low, 1 day
    ]);
  });

  it("hides dismissed items and surfaces the rest", async () => {
    dbMock.attentionAction.findMany.mockResolvedValue([
      {
        queue: "retraction_propagation",
        itemId: "triage-1",
        action: "dismiss",
        snoozedUntil: null,
        reason: "false positive",
        createdAt: new Date(NOW.getTime() - 2 * MS_PER_DAY),
      },
    ]);
    const listing = await listAttentionForFounder(tenant, NOW);
    const ids = listing.items.map((row) => row.itemId);
    expect(ids).not.toContain("triage-1");
    expect(ids[0]).toBe("drift-old-high");
  });

  it("hides snoozed items until the snooze expires", async () => {
    const snoozedAction = {
      queue: "drift" as const,
      itemId: "drift-fresh-low",
      action: "snooze" as const,
      snoozedUntil: new Date(NOW.getTime() + MS_PER_DAY),
      reason: "",
      createdAt: new Date(NOW.getTime() - 60_000),
    };
    dbMock.attentionAction.findMany.mockResolvedValue([snoozedAction]);

    const listingWhileSnoozed = await listAttentionForFounder(tenant, NOW);
    expect(
      listingWhileSnoozed.items.map((row) => row.itemId),
    ).not.toContain("drift-fresh-low");

    const after = new Date(NOW.getTime() + 2 * MS_PER_DAY);
    const listingAfter = await listAttentionForFounder(tenant, after);
    expect(listingAfter.items.map((row) => row.itemId)).toContain("drift-fresh-low");
  });
});

describe("attention API audit log", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (requireTenantContext as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(tenant);
    dbMock.attentionAction.create.mockResolvedValue({});
  });

  it("records dismissals with a reason", async () => {
    const req = new Request("http://localhost/api/founder/attention", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        queue: "drift",
        itemId: "drift-1",
        action: "dismiss",
        reason: "false positive",
      }),
    });
    const res = await POST(req);
    expect(res.status).toBe(200);
    const body = (await res.json()) as { ok: boolean; data: { action: string } };
    expect(body.ok).toBe(true);
    expect(body.data).toEqual({ action: "dismiss" });
    expect(dbMock.attentionAction.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        organizationId: tenant.organizationId,
        founderId: tenant.founderId,
        queue: "drift",
        itemId: "drift-1",
        action: "dismiss",
        reason: "false positive",
      }),
    });
  });

  it("rejects dismissals without a reason", async () => {
    const req = new Request("http://localhost/api/founder/attention", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        queue: "drift",
        itemId: "drift-1",
        action: "dismiss",
        reason: "",
      }),
    });
    const res = await POST(req);
    expect(res.status).toBe(400);
    expect(dbMock.attentionAction.create).not.toHaveBeenCalled();
  });

  it("rewrites a >14-day snooze as a dismissal with reason 'deferred indefinitely'", async () => {
    const tooLong = new Date(Date.now() + (MAX_SNOOZE_DAYS + 5) * MS_PER_DAY).toISOString();
    const req = new Request("http://localhost/api/founder/attention", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        queue: "drift",
        itemId: "drift-1",
        action: "snooze",
        snoozedUntil: tooLong,
      }),
    });
    const res = await POST(req);
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      ok: true;
      data: {
        action: string;
        rewrittenFromSnooze?: boolean;
        reason?: string;
      };
    };
    expect(body.data.action).toBe("dismiss");
    expect(body.data.rewrittenFromSnooze).toBe(true);
    expect(body.data.reason).toBe(DISMISS_REASON_DEFERRED);
    expect(dbMock.attentionAction.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        action: "dismiss",
        reason: DISMISS_REASON_DEFERRED,
      }),
    });
  });

  it("records snoozes inside the cap as snoozes, not dismissals", async () => {
    const within = new Date(Date.now() + 3 * MS_PER_DAY).toISOString();
    const req = new Request("http://localhost/api/founder/attention", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        queue: "drift",
        itemId: "drift-1",
        action: "snooze",
        snoozedUntil: within,
      }),
    });
    const res = await POST(req);
    expect(res.status).toBe(200);
    const body = (await res.json()) as { ok: true; data: { action: string } };
    expect(body.data.action).toBe("snooze");
    expect(dbMock.attentionAction.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        action: "snooze",
        snoozedUntil: expect.any(Date),
      }),
    });
  });
});

describe("loadAttentionActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("filters out actions for unknown queues", async () => {
    dbMock.attentionAction.findMany.mockResolvedValue([
      {
        queue: "drift",
        itemId: "a",
        action: "dismiss",
        snoozedUntil: null,
        reason: "x",
        createdAt: new Date(),
      },
      {
        queue: "made_up_queue",
        itemId: "b",
        action: "dismiss",
        snoozedUntil: null,
        reason: "x",
        createdAt: new Date(),
      },
    ]);
    const out = await loadAttentionActions(tenant);
    expect(out.map((row) => row.queue)).toEqual(["drift"]);
  });

  it("knows the canonical queue vocabulary", () => {
    expect(ATTENTION_QUEUES).toContain("drift");
    expect(ATTENTION_QUEUES).toContain("retraction_propagation");
    expect(ATTENTION_QUEUES).toContain("calibration_breach");
  });
});

describe("daily digest email", () => {
  it("only includes high-severity items and deeplinks to the dashboard", async () => {
    const recipient = {
      organizationId: "org-1",
      organizationSlug: "theseus-local",
      founderId: "founder-1",
      email: "founder@example.com",
      founderName: "Alpha",
      founderUsername: "alpha",
    };
    dbMock.driftEvent.findMany.mockResolvedValue([
      {
        id: "drift-high",
        observedAt: new Date(NOW.getTime() - 3 * MS_PER_DAY),
        severity: null,
        driftScore: 0.9,
        naturalLanguageSummary: "principle drift severe",
        notes: "",
        targetKind: "principle",
        targetId: "p1",
      },
      {
        id: "drift-low",
        observedAt: NOW,
        severity: null,
        driftScore: 0.1,
        naturalLanguageSummary: "principle drift mild",
        notes: "",
        targetKind: "principle",
        targetId: "p2",
      },
    ]);
    dbMock.reviewItem.findMany.mockResolvedValue([]);
    dbMock.sourceTriageItem.findMany.mockResolvedValue([]);
    dbMock.responseTriage.findMany.mockResolvedValue([]);
    dbMock.openQuestion.findMany.mockResolvedValue([]);
    dbMock.citationVerdict.findMany.mockResolvedValue([]);
    dbMock.attentionAction.findMany.mockResolvedValue([]);

    const payload = await buildDigestPayload(recipient, NOW);
    expect(payload.highSeverityItems.map((row) => row.itemId)).toEqual([
      "drift-high",
    ]);

    const email = buildDigestEmail(payload, {
      from: "notify@theseus.local",
      siteUrl: "https://theseuscodex.com",
    });
    expect(email.subject).toContain("1 item");
    expect(email.text).toContain("https://theseuscodex.com/dashboard");
    expect(email.text).toContain("principle drift severe");
    expect(email.text).not.toContain("principle drift mild");
    expect(email.html).toContain("https://theseuscodex.com/dashboard");
  });
});
