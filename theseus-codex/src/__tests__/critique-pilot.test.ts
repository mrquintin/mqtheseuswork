/**
 * Round-17 prompt 44 — open-critique pilot.
 *
 * The pilot stamps an inbound critique with a pilot tag + reviewer
 * slug when the per-reviewer pre-shared link is used. While the pilot
 * window is open, those rows sort to the top of the founder queue.
 * Non-pilot rows keep the existing severity-first ordering.
 *
 * The tests cover the load-bearing pieces:
 *   - Token resolution: unknown tokens do NOT silently promote a row.
 *   - Window gating: a closed window means no pilot tag is stamped
 *     even when the token is valid.
 *   - Queue ordering: pilot rows precede non-pilot pending rows.
 *   - Hall-of-fame consent: the public list filters by
 *     `hallOfFameConsent`, so a rejected critic-name-leak is
 *     prevented at the data-access layer.
 *   - Submit route end-to-end: the route forwards the resolved pilot
 *     tag through `createCritique`.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";

const dbMock = vi.hoisted(() => ({
  publishedConclusion: {
    findFirst: vi.fn(),
  },
  upload: {
    findFirst: vi.fn(),
  },
  critiqueSubmission: {
    count: vi.fn(),
    create: vi.fn(),
    findMany: vi.fn(),
  },
}));

vi.mock("@/lib/db", () => ({ db: dbMock }));

import { POST as submitPOST } from "@/app/api/public/critique/submit/route";
import {
  applyPilotPriority,
  listAcceptedCritiques,
} from "@/lib/critiquesApi";
import {
  isPilotWindowOpen,
  loadPilotConfig,
  parseReviewers,
  parseWindow,
  PILOT_TAG,
  pilotAcceptRate,
  pilotSeverityDistribution,
  resolveReviewerSlug,
} from "@/lib/critiquePilot";

const PILOT_ENV_KEYS = [
  "THESEUS_CRITIQUE_PILOT_REVIEWERS",
  "THESEUS_CRITIQUE_PILOT_WINDOW",
];
const ORIGINAL_ENV = Object.fromEntries(
  PILOT_ENV_KEYS.map((k) => [k, process.env[k]]),
);

function restoreEnv() {
  for (const k of PILOT_ENV_KEYS) {
    if (ORIGINAL_ENV[k] === undefined) delete process.env[k];
    else process.env[k] = ORIGINAL_ENV[k];
  }
}

function jsonRequest(body: Record<string, unknown>, url = "http://localhost:3000/api/public/critique/submit") {
  return new Request(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Origin: "https://theseuscodex.com",
    },
    body: JSON.stringify(body),
  }) as unknown as NextRequest;
}

function validCritiqueBody(extra: Record<string, unknown> = {}) {
  return {
    articleSlug: "qh-benchmark-v1-results",
    targetClaim: "Headline metric collapses on the held-out cohort",
    counterEvidence:
      "Re-ran the benchmark on the public Theseus artifact set against a held-out cohort drawn from the published evaluation harness; the reported headline metric drops by 18 points, well outside the published confidence interval. This is a structural disagreement with the v1 cut.",
    derivationMethod:
      "Direct replication on a held-out cohort, scripted in Python with the published evaluation harness; ran three seeds to confirm.",
    citations: "https://example.org/reviewer-a/qh-replication",
    submitterEmail: "reviewer-a@example.org",
    displayName: "Reviewer A",
    publicUrl: "https://example.org/reviewer-a",
    ...extra,
  };
}

describe("critique pilot config", () => {
  it("parses a reviewer list of slug:token pairs", () => {
    const reviewers = parseReviewers("slug-a:token-a,slug-b:token-b , slug-c:token-c");
    expect(reviewers).toEqual([
      { slug: "slug-a", token: "token-a" },
      { slug: "slug-b", token: "token-b" },
      { slug: "slug-c", token: "token-c" },
    ]);
  });

  it("rejects malformed reviewer entries silently", () => {
    expect(parseReviewers("not-a-pair,:no-slug,no-token:,ok:tok")).toEqual([
      { slug: "ok", token: "tok" },
    ]);
  });

  it("parses an ISO window and treats unparseable input as fully open", () => {
    const w = parseWindow("2026-05-15T00:00:00Z..2026-06-15T00:00:00Z");
    expect(w.startsAt).toBeInstanceOf(Date);
    expect(w.endsAt).toBeInstanceOf(Date);
    expect(parseWindow("garbage")).toEqual({ startsAt: null, endsAt: null });
    expect(parseWindow(undefined)).toEqual({ startsAt: null, endsAt: null });
  });

  it("treats an empty window as open and bounded windows correctly", () => {
    expect(isPilotWindowOpen({ startsAt: null, endsAt: null })).toBe(true);
    const past = new Date("2020-01-01T00:00:00Z");
    const future = new Date("2099-01-01T00:00:00Z");
    expect(isPilotWindowOpen({ startsAt: future, endsAt: null })).toBe(false);
    expect(isPilotWindowOpen({ startsAt: null, endsAt: past })).toBe(false);
    expect(isPilotWindowOpen({ startsAt: past, endsAt: future })).toBe(true);
  });

  it("resolveReviewerSlug requires an exact token match — no silent promotion", () => {
    const config = {
      tag: PILOT_TAG,
      window: { startsAt: null, endsAt: null },
      reviewers: [{ slug: "reviewer-a", token: "tok-a" }],
    };
    expect(resolveReviewerSlug(config, "tok-a")).toBe("reviewer-a");
    expect(resolveReviewerSlug(config, "tok-A")).toBeNull();
    expect(resolveReviewerSlug(config, "")).toBeNull();
    expect(resolveReviewerSlug(config, null)).toBeNull();
    expect(resolveReviewerSlug(config, "tok-unknown")).toBeNull();
  });

  it("loadPilotConfig reads env vars", () => {
    process.env.THESEUS_CRITIQUE_PILOT_REVIEWERS = "x:1,y:2";
    process.env.THESEUS_CRITIQUE_PILOT_WINDOW = "2026-05-15T00:00:00Z..2026-06-15T00:00:00Z";
    const cfg = loadPilotConfig();
    expect(cfg.tag).toBe(PILOT_TAG);
    expect(cfg.reviewers).toEqual([
      { slug: "x", token: "1" },
      { slug: "y", token: "2" },
    ]);
    expect(cfg.window.startsAt).toBeInstanceOf(Date);
    restoreEnv();
  });
});

describe("pilot priority sort", () => {
  function row(
    overrides: Partial<{
      id: string;
      status: string;
      pilotTag: string;
      createdAt: Date;
    }>,
  ) {
    return {
      id: "row-x",
      status: "pending",
      pilotTag: "",
      createdAt: new Date("2026-05-14T12:00:00Z"),
      ...overrides,
    };
  }

  it("routes pilot pending rows to the top when the window is open", () => {
    const rows = [
      row({ id: "older-non-pilot", createdAt: new Date("2026-05-10T00:00:00Z") }),
      row({ id: "newer-pilot", pilotTag: PILOT_TAG, createdAt: new Date("2026-05-13T00:00:00Z") }),
      row({ id: "newer-non-pilot", createdAt: new Date("2026-05-14T00:00:00Z") }),
      row({ id: "decided", status: "accepted", createdAt: new Date("2026-05-09T00:00:00Z") }),
    ];
    const sorted = applyPilotPriority(rows, PILOT_TAG, true);
    expect(sorted.map((r) => r.id)).toEqual([
      "newer-pilot",
      "older-non-pilot",
      "newer-non-pilot",
      "decided",
    ]);
  });

  it("does nothing when the pilot window is closed", () => {
    const rows = [
      row({ id: "n", createdAt: new Date("2026-05-10") }),
      row({ id: "p", pilotTag: PILOT_TAG, createdAt: new Date("2026-05-13") }),
    ];
    const sorted = applyPilotPriority(rows, PILOT_TAG, false);
    expect(sorted.map((r) => r.id)).toEqual(["n", "p"]);
  });

  it("does nothing when no pilot tag is provided", () => {
    const rows = [
      row({ id: "n" }),
      row({ id: "p", pilotTag: PILOT_TAG }),
    ];
    expect(applyPilotPriority(rows, "", true).map((r) => r.id)).toEqual(["n", "p"]);
  });

  it("orders pilot rows oldest-first so reviewers don't wait", () => {
    const rows = [
      row({ id: "newer", pilotTag: PILOT_TAG, createdAt: new Date("2026-05-13") }),
      row({ id: "older", pilotTag: PILOT_TAG, createdAt: new Date("2026-05-10") }),
    ];
    expect(applyPilotPriority(rows, PILOT_TAG, true).map((r) => r.id)).toEqual([
      "older",
      "newer",
    ]);
  });
});

describe("pilot debrief helpers", () => {
  const submissions = [
    { status: "accepted", severityLabel: "high", pilotReviewerSlug: "a", hallOfFameConsent: true },
    { status: "accepted", severityLabel: "medium", pilotReviewerSlug: "b", hallOfFameConsent: false },
    { status: "rejected", severityLabel: "", pilotReviewerSlug: "a", hallOfFameConsent: false },
    { status: "pending", severityLabel: "", pilotReviewerSlug: "c", hallOfFameConsent: false },
  ];

  it("computes accept rate as accepted / total (including rejected and pending)", () => {
    expect(pilotAcceptRate(submissions)).toBeCloseTo(2 / 4);
    expect(pilotAcceptRate([])).toBe(0);
  });

  it("groups severity over accepted rows only", () => {
    expect(pilotSeverityDistribution(submissions)).toEqual({
      low: 0,
      medium: 1,
      high: 1,
      unscored: 0,
    });
  });
});

describe("POST /api/public/critique/submit pilot tagging", () => {
  const publishedConclusion = {
    id: "pub-1",
    organizationId: "org-1",
    slug: "qh-benchmark-v1-results",
  };

  beforeEach(() => {
    vi.clearAllMocks();
    dbMock.publishedConclusion.findFirst.mockResolvedValue(publishedConclusion);
    dbMock.upload.findFirst.mockResolvedValue(null);
    dbMock.critiqueSubmission.count.mockResolvedValue(0);
    dbMock.critiqueSubmission.create.mockImplementation(async ({ data }: { data: Record<string, unknown> }) => ({
      id: "critique-1",
      ...data,
      publishedConclusionId: data.publishedConclusionId ?? null,
      moderatorNote: "",
      severityLabel: "",
      severityValue: 0,
      decidedById: null,
      decidedAt: null,
      triggeredRevisionId: null,
      addendumId: null,
      createdAt: new Date("2026-05-14T12:00:00Z"),
      updatedAt: new Date("2026-05-14T12:00:00Z"),
    }));
  });

  it("stamps the pilot tag when a valid token is presented and the window is open", async () => {
    process.env.THESEUS_CRITIQUE_PILOT_REVIEWERS = "reviewer-a:tok-a";
    process.env.THESEUS_CRITIQUE_PILOT_WINDOW = "";

    const res = await submitPOST(jsonRequest(validCritiqueBody({ pilotToken: "tok-a", hallOfFameConsent: true })));
    expect(res.status).toBe(200);

    expect(dbMock.critiqueSubmission.create).toHaveBeenCalledTimes(1);
    const callArg = dbMock.critiqueSubmission.create.mock.calls[0][0] as { data: Record<string, unknown> };
    expect(callArg.data.pilotTag).toBe(PILOT_TAG);
    expect(callArg.data.pilotReviewerSlug).toBe("reviewer-a");
    expect(callArg.data.hallOfFameConsent).toBe(true);
    restoreEnv();
  });

  it("does NOT stamp the pilot tag for an unknown token (no silent promotion)", async () => {
    process.env.THESEUS_CRITIQUE_PILOT_REVIEWERS = "reviewer-a:tok-a";

    const res = await submitPOST(jsonRequest(validCritiqueBody({ pilotToken: "tok-imposter" })));
    expect(res.status).toBe(200);

    const callArg = dbMock.critiqueSubmission.create.mock.calls[0][0] as { data: Record<string, unknown> };
    expect(callArg.data.pilotTag).toBe("");
    expect(callArg.data.pilotReviewerSlug).toBe("");
    expect(callArg.data.hallOfFameConsent).toBe(false);
    restoreEnv();
  });

  it("does NOT stamp the pilot tag when the window has closed", async () => {
    process.env.THESEUS_CRITIQUE_PILOT_REVIEWERS = "reviewer-a:tok-a";
    process.env.THESEUS_CRITIQUE_PILOT_WINDOW = "2020-01-01T00:00:00Z..2020-12-31T00:00:00Z";

    const res = await submitPOST(jsonRequest(validCritiqueBody({ pilotToken: "tok-a" })));
    expect(res.status).toBe(200);

    const callArg = dbMock.critiqueSubmission.create.mock.calls[0][0] as { data: Record<string, unknown> };
    expect(callArg.data.pilotTag).toBe("");
    expect(callArg.data.pilotReviewerSlug).toBe("");
    restoreEnv();
  });

  it("accepts the token from the ?pilot= query parameter", async () => {
    process.env.THESEUS_CRITIQUE_PILOT_REVIEWERS = "reviewer-b:tok-b";
    const url = "http://localhost:3000/api/public/critique/submit?pilot=tok-b";
    const res = await submitPOST(jsonRequest(validCritiqueBody(), url));
    expect(res.status).toBe(200);

    const callArg = dbMock.critiqueSubmission.create.mock.calls[0][0] as { data: Record<string, unknown> };
    expect(callArg.data.pilotReviewerSlug).toBe("reviewer-b");
    expect(callArg.data.pilotTag).toBe(PILOT_TAG);
    restoreEnv();
  });

  it("hallOfFameConsent defaults to false when omitted", async () => {
    const res = await submitPOST(jsonRequest(validCritiqueBody()));
    expect(res.status).toBe(200);
    const callArg = dbMock.critiqueSubmission.create.mock.calls[0][0] as { data: Record<string, unknown> };
    expect(callArg.data.hallOfFameConsent).toBe(false);
  });
});

describe("listAcceptedCritiques hall-of-fame consent filter", () => {
  it("queries with hallOfFameConsent = true", async () => {
    dbMock.critiqueSubmission.findMany.mockResolvedValue([]);
    await listAcceptedCritiques();
    expect(dbMock.critiqueSubmission.findMany).toHaveBeenCalledWith({
      where: { status: "accepted", hallOfFameConsent: true },
      orderBy: { decidedAt: "desc" },
    });
  });
});
