import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { rankResults, textScore } from "@/lib/search";

/**
 * Round 21 — principle surfaces: index + detail + cross-surface search
 * ranking.
 *
 * The three things this file pins down:
 *
 *   1. The /principles index renders with three filter dimensions
 *      (kind, domain, conviction) wired to URL search params.
 *   2. The /principles/[id] detail renders all six "evidence layers"
 *      when data is present, and hides any section whose underlying
 *      data is empty (no empty boxes on the public surface).
 *   3. The search ranker promotes principles over conclusions over
 *      claims on a fixture corpus — the same query returns the
 *      principle first even when a conclusion has a longer textual
 *      match.
 */

// ── Shared mocks ──────────────────────────────────────────────────────

const dbMock = vi.hoisted(() => ({
  principle: { findFirst: vi.fn(), findMany: vi.fn() },
  conclusion: { findMany: vi.fn() },
  quantitativeFormalisation: { findMany: vi.fn(), findFirst: vi.fn() },
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: ReactNode;
    href: string;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("notFound called");
  },
  permanentRedirect: (target: string) => {
    throw new Error(`permanentRedirect(${target})`);
  },
}));

vi.mock("@/components/PublicHeader", () => ({
  default: ({ authed }: { authed: boolean }) => (
    <header data-authed={String(authed)}>public header</header>
  ),
}));

vi.mock("@/lib/auth", () => ({
  getFounder: vi.fn(async () => null),
}));

vi.mock("@/lib/db", () => ({ db: dbMock }));

// ── Helpers ───────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
});

function principleRowFixture(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "principle-1",
    organizationId: "org-1",
    text: "Methods that beat predict-the-mean must beat it after costs.",
    domainsJson: JSON.stringify(["forecasting", "policy"]),
    clusterConclusionIds: JSON.stringify(["c1", "c2"]),
    citedConclusionIds: JSON.stringify(["c1"]),
    status: "accepted",
    triageReason: "",
    mergedIntoId: null,
    convictionScore: 0.72,
    domainBreadth: 2,
    clusterCentroidSimilarity: 0.81,
    publicVisible: true,
    driftReason: null,
    reviewedAt: new Date("2026-04-01T00:00:00Z"),
    publishedAt: new Date("2026-04-02T00:00:00Z"),
    createdAt: new Date("2026-03-01T00:00:00Z"),
    updatedAt: new Date("2026-04-02T00:00:00Z"),
    ...overrides,
  };
}

// ── 1. Index page ─────────────────────────────────────────────────────

describe("/principles index", () => {
  it("renders the three filter dimensions wired to URL params", async () => {
    dbMock.principle.findMany.mockResolvedValueOnce([principleRowFixture()]);
    // `listPublicPrinciples` hydrates underlying conclusions first; then
    // `loadEnrichedPrinciples` queries the same table for the kind
    // aggregation. Both calls get the same fixture.
    dbMock.conclusion.findMany.mockResolvedValue([
      { id: "c1", text: "c1 text", confidenceTier: "firm", principleKind: "RULE" },
      {
        id: "c2",
        text: "c2 text",
        confidenceTier: "founder",
        principleKind: "RULE",
      },
    ]);
    dbMock.quantitativeFormalisation.findMany.mockResolvedValueOnce([
      { principleId: "principle-1" },
    ]);

    const { default: PrinciplesIndexPage } = await import(
      "@/app/principles/page"
    );
    const element = await PrinciplesIndexPage({
      searchParams: Promise.resolve({}),
    });
    const html = renderToStaticMarkup(element);

    // The three required filter dimensions all wire to /principles?... links.
    expect(html).toContain('data-testid="filter-kind"');
    expect(html).toContain('data-testid="filter-domain"');
    expect(html).toContain('data-testid="filter-quantified"');
    // Bonus dimension also present (conviction); confirms it is wired.
    expect(html).toContain('data-testid="filter-conviction"');
    // Filter chips link to /principles?kind=... etc.
    expect(html).toContain("/principles?kind=RULE");
    expect(html).toContain("/principles?domain=forecasting");
    expect(html).toContain("/principles?quantified=1");
    // The fixture principle renders.
    expect(html).toContain(
      "Methods that beat predict-the-mean must beat it after costs.",
    );
    // Kind badge is derived from the underlying conclusions' principleKind.
    expect(html).toContain('data-testid="principle-kind-badge"');
    expect(html).toMatch(/rule/);
    // Approved formalisation badge shows for the one principle with an
    // APPROVED row.
    expect(html).toContain('data-testid="principle-quantified-badge"');
  });

  it("applies the kind filter from search params", async () => {
    dbMock.principle.findMany.mockResolvedValueOnce([
      principleRowFixture(),
      principleRowFixture({
        id: "principle-2",
        text: "Different shape principle",
        clusterConclusionIds: JSON.stringify(["c3"]),
      }),
    ]);
    dbMock.conclusion.findMany.mockResolvedValue([
      { id: "c1", text: "c1", confidenceTier: "firm", principleKind: "RULE" },
      { id: "c2", text: "c2", confidenceTier: "firm", principleKind: "RULE" },
      {
        id: "c3",
        text: "c3",
        confidenceTier: "firm",
        principleKind: "HEURISTIC",
      },
    ]);
    dbMock.quantitativeFormalisation.findMany.mockResolvedValueOnce([]);

    const { default: PrinciplesIndexPage } = await import(
      "@/app/principles/page"
    );
    const element = await PrinciplesIndexPage({
      searchParams: Promise.resolve({ kind: "HEURISTIC" }),
    });
    const html = renderToStaticMarkup(element);

    // Only the heuristic row survives.
    expect(html).toContain("Different shape principle");
    expect(html).not.toContain("Methods that beat predict-the-mean");
  });
});

// ── 2. Detail page — section visibility ───────────────────────────────

describe("/principles/[id] detail", () => {
  function clusterConclusionsFixture() {
    return [
      {
        id: "c1",
        text: "Linker holds up on the held-out tournament shard.",
        confidenceTier: "firm",
        confidence: 0.82,
        principleKind: "RULE",
        domainOfApplicability: "forecasting",
        decisionExamples: JSON.stringify([
          "Whether to route a new method through full peer review",
        ]),
        sourceSpan: "predict-the-mean baseline holds the line",
        topicHint: "methods",
        sources: [
          {
            upload: {
              id: "u1",
              title: "Methods Q1 review",
              slug: "methods-q1-review",
              publishedAt: new Date("2026-03-15T00:00:00Z"),
              visibility: "public",
            },
          },
        ],
      },
      {
        id: "c2",
        text: "Method failed on the unseen shard — keep at open tier.",
        confidenceTier: "open",
        confidence: 0.3,
        principleKind: "RULE",
        domainOfApplicability: "forecasting",
        decisionExamples: JSON.stringify([]),
        sourceSpan: null,
        topicHint: "methods",
        sources: [],
      },
    ];
  }

  it("renders all sections when data is present", async () => {
    dbMock.principle.findFirst.mockResolvedValueOnce(principleRowFixture());
    dbMock.conclusion.findMany.mockResolvedValueOnce(
      clusterConclusionsFixture(),
    );
    // Approved formalisation present.
    dbMock.quantitativeFormalisation.findFirst.mockResolvedValueOnce({
      id: "qf-1",
      organizationId: "org-1",
      principleId: "principle-1",
      status: "APPROVED",
      nullHypothesis:
        "The method does not beat predict-the-mean after costs (skill ≤ 0).",
      metricsJson: JSON.stringify([
        {
          name: "skill",
          definition: "MAE-relative skill",
          unit: "ratio",
          source_dataset: "tournament shard",
          update_cadence: "weekly",
        },
      ]),
      testsJson: JSON.stringify([
        {
          kind: "regression",
          dependent: "skill",
          independents: ["method"],
          controls: [],
          dataset_filter: "post-2025",
          expected_sign_or_magnitude: ">0",
          expected_p_threshold: 0.05,
        },
      ]),
      dataSourcesJson: JSON.stringify([
        {
          name: "tournament shard",
          provenance: "noosphere held-out",
          license: "CC-BY",
          refresh_cadence: "weekly",
        },
      ]),
      decisionThresholdsJson: JSON.stringify([
        "Retire the method if skill < 0 for three consecutive shards.",
      ]),
      unformalisableReason: null,
      drafterModel: "claude-opus-4-7",
      drafterNotes: "",
      reviewedByFounderId: "f-1",
      reviewedAt: new Date("2026-04-05T00:00:00Z"),
      createdAt: new Date("2026-04-01T00:00:00Z"),
      updatedAt: new Date("2026-04-05T00:00:00Z"),
    });

    const { default: PrincipleDetailPage } = await import(
      "@/app/principles/[id]/page"
    );
    const element = await PrincipleDetailPage({
      params: Promise.resolve({ id: "principle-1" }),
    });
    const html = renderToStaticMarkup(element);

    expect(html).toContain('data-testid="principle-statement"');
    expect(html).toContain('data-testid="principle-kind-badge"');
    expect(html).toContain('data-testid="section-formalisation"');
    expect(html).toContain('data-testid="section-evidence-for"');
    expect(html).toContain('data-testid="section-evidence-against"');
    expect(html).toContain('data-testid="section-decisions"');
    expect(html).toContain('data-testid="section-sources"');
    expect(html).toContain('data-testid="section-lineage"');
    // Quoted span preserved verbatim per the citation contract.
    expect(html).toContain('data-testid="quoted-span"');
    expect(html).toContain("predict-the-mean baseline holds the line");
  });

  it("hides sections whose data is empty (no empty boxes)", async () => {
    dbMock.principle.findFirst.mockResolvedValueOnce(
      principleRowFixture({
        clusterConclusionIds: JSON.stringify([]),
        citedConclusionIds: JSON.stringify([]),
      }),
    );
    dbMock.conclusion.findMany.mockResolvedValueOnce([]);
    dbMock.quantitativeFormalisation.findFirst.mockResolvedValueOnce(null);

    const { default: PrincipleDetailPage } = await import(
      "@/app/principles/[id]/page"
    );
    const element = await PrincipleDetailPage({
      params: Promise.resolve({ id: "principle-1" }),
    });
    const html = renderToStaticMarkup(element);

    // Statement + meta always render.
    expect(html).toContain('data-testid="principle-statement"');
    expect(html).toContain('data-testid="principle-kind-badge"');
    // Every dependent section omitted when empty.
    expect(html).not.toContain('data-testid="section-formalisation"');
    expect(html).not.toContain('data-testid="section-evidence-for"');
    expect(html).not.toContain('data-testid="section-evidence-against"');
    expect(html).not.toContain('data-testid="section-decisions"');
    expect(html).not.toContain('data-testid="section-sources"');
    expect(html).not.toContain('data-testid="section-lineage"');
  });
});

// ── 3. Search ranking ─────────────────────────────────────────────────

describe("rankResults", () => {
  it("ranks principles above conclusions above claims on a fixture corpus", () => {
    // A conclusion has a longer body that mentions the query phrase
    // repeatedly; the principle is a short slogan with one match.
    // Round 21's ranker still puts the principle first.
    const corpus = [
      {
        id: "claim-1",
        kind: "claim" as const,
        text: "We saw method drift on the new shard, looks bad for the linker.",
      },
      {
        id: "conclusion-1",
        kind: "conclusion" as const,
        text: "After costs, the method that beat the baseline last quarter no longer beats predict-the-mean — beats baseline only on a re-weighted holdout sample.",
      },
      {
        id: "principle-1",
        kind: "principle" as const,
        text: "A method must beat predict-the-mean after costs.",
      },
      {
        id: "principle-2",
        kind: "principle" as const,
        text: "Always discount conviction by reviewer disagreement.",
      },
    ];

    const ranked = rankResults("beat predict-the-mean after costs", corpus);
    // The matching principle is first.
    expect(ranked[0]?.id).toBe("principle-1");
    // The matching conclusion is second.
    expect(ranked[1]?.id).toBe("conclusion-1");
    // The unrelated principle and unrelated claim drop out (zero
    // text-score candidates are removed).
    const ids = ranked.map((r) => r.id);
    expect(ids).not.toContain("principle-2");
    // The kind ordering principles > conclusions > claims holds across
    // any returned matches. Tier numbers ascend with lower rank, so the
    // sequence must be monotonically non-decreasing.
    const kindOrder = ranked.map((r) => r.kind);
    let lastTier = 0;
    for (const k of kindOrder) {
      const tier = k === "principle" ? 0 : k === "conclusion" ? 1 : 2;
      expect(tier).toBeGreaterThanOrEqual(lastTier);
      lastTier = tier;
    }
  });

  it("textScore is zero when the query has no matching tokens", () => {
    expect(textScore("nothing matches", "completely different text")).toBe(0);
    expect(textScore("", "anything")).toBe(0);
    expect(textScore("phrase", "")).toBe(0);
  });

  it("returns no results for an empty query (no fallback listings)", () => {
    expect(rankResults("", [{ id: "x", kind: "principle", text: "hi" }])).toEqual(
      [],
    );
    expect(
      rankResults("   ", [{ id: "x", kind: "principle", text: "hi" }]),
    ).toEqual([]);
  });
});
