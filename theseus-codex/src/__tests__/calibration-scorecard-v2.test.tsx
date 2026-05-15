import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Round 22 — public calibration scorecard v2.
 *
 * Synthetic resolution sets exercise the edge cases that decide whether
 * the page is trustworthy: tiny n, all-correct, all-wrong, perfectly
 * calibrated, anti-calibrated. The assertion in every case is the same —
 * the page renders *honestly*: it never prints a point estimate the
 * sample cannot support, the comparators always stand, and every
 * resolved forecast in the numerator is one click from its record.
 */

const hoisted = vi.hoisted(() => ({ loadMock: vi.fn() }));

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

vi.mock("@/components/PublicHeader", () => ({
  default: ({ authed }: { authed: boolean }) => (
    <header data-authed={String(authed)}>Public header</header>
  ),
}));

vi.mock("@/lib/auth", () => ({
  getFounder: vi.fn(async () => null),
}));

vi.mock("@/lib/db", () => ({ db: {} }));

vi.mock("@/lib/calibrationData", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/calibrationData")>();
  return { ...actual, loadPublicCalibrationManifest: hoisted.loadMock };
});

import CalibrationComparators from "@/components/CalibrationComparators";
import CalibrationPlot from "@/components/CalibrationPlot";
import CalibrationSliceFilter from "@/components/CalibrationSliceFilter";
import CalibrationPage from "@/app/calibration/page";
import {
  HEADLINE_MIN_N,
  bootstrapMeanCi,
  horizonKeyForDays,
  makeHeadlineBrier,
  type PublicCalibrationManifest,
  type ReliabilityBin,
  type ResolvedAuditEntry,
} from "@/lib/calibrationData";

// ── Synthetic fixtures ────────────────────────────────────────────────────

type Row = { id: string; p: number; outcome: "YES" | "NO" };

function brierOf(p: number, outcome: "YES" | "NO"): number {
  const y = outcome === "YES" ? 1 : 0;
  return (p - y) ** 2;
}

function mkManifest(
  overrides: Partial<PublicCalibrationManifest> = {},
): PublicCalibrationManifest {
  return {
    schema: "theseus.public_calibration.manifest",
    schemaVersion: 1,
    generatedAt: "2026-05-14T00:00:00Z",
    source: "manifest",
    publishHorizonDays: 14,
    sparseBinThreshold: 5,
    bootstrapIterations: 400,
    ciLevel: 0.9,
    binCount: 10,
    counts: {
      total: 0,
      resolvedBinary: 0,
      withdrawn: 0,
      staleUnresolved: 0,
      continuous: 0,
    },
    withdrawnRate: null,
    resolutionSetHash: "deadbeef",
    binaryMetricName: "brier_score",
    continuousMetricName: "quadratic_loss",
    aggregateBrier: [],
    calibrationCurve: [],
    calibrationSlope: { slope: null, ciLow: null, ciHigh: null, sampleSize: 0 },
    decileBest: [],
    decileWorst: [],
    continuousQuadraticLoss: null,
    domains: [],
    methods: [],
    venues: [],
    horizons: [],
    headlineBrier: makeHeadlineBrier(null, 0, { ciLow: null, ciHigh: null }),
    outcomeBaseRate: null,
    resolvedIndex: [],
    resolvedIndexComplete: true,
    filter: {
      domain: null,
      methodName: null,
      methodVersion: null,
      venue: null,
      horizon: null,
    },
    notes: [],
    ...overrides,
  };
}

function manifestFromRows(
  rows: Row[],
  extra: Partial<PublicCalibrationManifest> = {},
): PublicCalibrationManifest {
  const briers = rows.map((r) => brierOf(r.p, r.outcome));
  const mean = briers.length
    ? briers.reduce((a, b) => a + b, 0) / briers.length
    : null;
  const n = rows.length;
  const baseRate = n
    ? rows.filter((r) => r.outcome === "YES").length / n
    : null;
  const resolvedIndex: ResolvedAuditEntry[] = rows.map((r, i) => ({
    predictionId: r.id,
    headline: `Forecast ${r.id}`,
    marketTitle: `Market ${r.id}`,
    marketUrl:
      i % 2 === 0
        ? `https://polymarket.com/event/${r.id}`
        : `https://kalshi.com/markets/${r.id}`,
    domain: "geopolitics",
    venue: i % 2 === 0 ? "Polymarket" : "Kalshi",
    methodName: null,
    methodVersion: null,
    probabilityYes: r.p,
    outcome: r.outcome,
    brier: brierOf(r.p, r.outcome),
    resolvedAt: "2026-05-01T00:00:00Z",
  }));
  return mkManifest({
    counts: {
      total: n,
      resolvedBinary: n,
      withdrawn: 0,
      staleUnresolved: 0,
      continuous: 0,
    },
    aggregateBrier: [
      { label: "all-time", days: null, n, meanBrier: mean, meanLogLoss: null },
    ],
    headlineBrier: makeHeadlineBrier(mean, n, bootstrapMeanCi(briers)),
    outcomeBaseRate: baseRate,
    resolvedIndex,
    ...extra,
  });
}

function repeatRows(p: number, outcome: "YES" | "NO", count: number): Row[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `pred_${outcome}_${p}_${i}`,
    p,
    outcome,
  }));
}

function bin(
  lo: number,
  hi: number,
  n: number,
  meanPredicted: number | null,
  observedFrequency: number | null,
  ci: [number, number] | null,
): ReliabilityBin {
  return {
    lo,
    hi,
    n,
    meanPredicted,
    observedFrequency,
    ciLow: ci ? ci[0] : null,
    ciHigh: ci ? ci[1] : null,
    sparse: n > 0 && n < 5,
  };
}

async function renderPage(
  manifest: PublicCalibrationManifest,
  searchParams: Record<string, string> = {},
): Promise<string> {
  hoisted.loadMock.mockResolvedValue(manifest);
  const element = await CalibrationPage({
    searchParams: Promise.resolve(searchParams),
  });
  return renderToStaticMarkup(element);
}

beforeEach(() => {
  hoisted.loadMock.mockReset();
});

// ── Pure helpers ──────────────────────────────────────────────────────────

describe("calibration pure helpers", () => {
  it("bootstrapMeanCi returns nulls for an empty sample", () => {
    expect(bootstrapMeanCi([])).toEqual({ ciLow: null, ciHigh: null });
  });

  it("bootstrapMeanCi collapses to the value for a constant sample", () => {
    const ci = bootstrapMeanCi([0.04, 0.04, 0.04, 0.04, 0.04]);
    expect(ci.ciLow).toBeCloseTo(0.04, 10);
    expect(ci.ciHigh).toBeCloseTo(0.04, 10);
  });

  it("bootstrapMeanCi is deterministic and brackets the sample mean", () => {
    const sample = [0.01, 0.05, 0.1, 0.2, 0.3, 0.02, 0.15, 0.25];
    const mean = sample.reduce((a, b) => a + b, 0) / sample.length;
    const a = bootstrapMeanCi(sample);
    const b = bootstrapMeanCi(sample);
    expect(a).toEqual(b);
    expect(a.ciLow!).toBeLessThanOrEqual(mean);
    expect(a.ciHigh!).toBeGreaterThanOrEqual(mean);
  });

  it("makeHeadlineBrier gates stability on HEADLINE_MIN_N", () => {
    expect(makeHeadlineBrier(0.18, HEADLINE_MIN_N - 1, { ciLow: 0.1, ciHigh: 0.25 }).stable).toBe(
      false,
    );
    expect(makeHeadlineBrier(0.18, HEADLINE_MIN_N, { ciLow: 0.1, ciHigh: 0.25 }).stable).toBe(true);
    // A missing point estimate is never "stable", regardless of n.
    expect(makeHeadlineBrier(null, 1000, { ciLow: null, ciHigh: null }).stable).toBe(false);
  });

  it("horizonKeyForDays buckets elapsed time", () => {
    expect(horizonKeyForDays(3)).toBe("lt7");
    expect(horizonKeyForDays(20)).toBe("8-30");
    expect(horizonKeyForDays(60)).toBe("31-90");
    expect(horizonKeyForDays(400)).toBe("gt90");
  });
});

// ── Edge-case resolution sets: the page must render honestly ──────────────

describe("calibration scorecard — synthetic resolution sets", () => {
  it("tiny n: suppresses the point estimate, shows the count instead", async () => {
    const rows = [
      { id: "tiny_a", p: 0.7, outcome: "YES" as const },
      { id: "tiny_b", p: 0.3, outcome: "NO" as const },
      { id: "tiny_c", p: 0.6, outcome: "NO" as const },
      { id: "tiny_d", p: 0.55, outcome: "YES" as const },
    ];
    const manifest = manifestFromRows(rows);
    expect(manifest.headlineBrier.stable).toBe(false);

    const html = await renderPage(manifest);
    expect(html).toContain("too few resolutions for a stable score");
    expect(html).toContain("n = 4");
    // The hero must not promote the working mean to a headline number.
    expect(html).not.toContain("font-size:2.6rem");
    // Comparators still render; the firm row is explicitly withheld.
    expect(html).toContain("Withheld");
    // Every resolved forecast is still reachable.
    for (const row of rows) {
      expect(html).toContain(`/forecasts/${row.id}`);
    }
  });

  it("empty resolution set renders honestly with no fabricated numbers", async () => {
    const manifest = manifestFromRows([]);
    const html = await renderPage(manifest);
    expect(html).toContain("too few resolutions for a stable score");
    expect(html).toContain("n = 0");
    expect(html).toContain("No resolved forecasts yet");
  });

  it("all-correct: reports a near-zero Brier with CI once n clears the floor", async () => {
    const rows = [...repeatRows(0.98, "YES", 18), ...repeatRows(0.02, "NO", 18)];
    const manifest = manifestFromRows(rows);
    expect(manifest.headlineBrier.stable).toBe(true);
    expect(manifest.headlineBrier.meanBrier!).toBeCloseTo(0.0004, 6);

    const html = await renderPage(manifest);
    expect(html).toContain("0.000");
    expect(html).toContain("bootstrap CI");
    expect(html).toContain(`n = ${rows.length} resolved forecasts`);
  });

  it("all-wrong: reports a near-one Brier without flinching", async () => {
    const rows = [...repeatRows(0.98, "NO", 30)];
    const manifest = manifestFromRows(rows);
    expect(manifest.headlineBrier.stable).toBe(true);
    expect(manifest.headlineBrier.meanBrier!).toBeCloseTo(0.9604, 4);

    const html = await renderPage(manifest);
    expect(html).toContain("0.960");
    // The comparator panel still anchors against the 0.25 baselines.
    expect(html).toContain("Random guessing");
    expect(html).toContain("Always forecast 50%");
  });

  it("perfectly calibrated: reliability diagram renders on the diagonal", async () => {
    const rows = [...repeatRows(0.5, "YES", 20), ...repeatRows(0.5, "NO", 20)];
    const curve = [
      bin(0.0, 0.2, 10, 0.1, 0.1, [0.02, 0.2]),
      bin(0.2, 0.4, 12, 0.3, 0.3, [0.18, 0.43]),
      bin(0.4, 0.6, 14, 0.5, 0.5, [0.36, 0.64]),
      bin(0.6, 0.8, 10, 0.7, 0.7, [0.55, 0.84]),
      bin(0.8, 1.0, 9, 0.9, 0.9, [0.78, 0.99]),
    ];
    const manifest = manifestFromRows(rows, {
      calibrationCurve: curve,
      calibrationSlope: { slope: 1.0, ciLow: 0.88, ciHigh: 1.12, sampleSize: 40 },
    });
    const html = await renderPage(manifest);
    expect(html).toContain("Reliability diagram");
    expect(html).toContain("perfect calibration");
    // Every bin is labelled with its sample size.
    expect(html).toContain("n=10");
    expect(html).toContain("n=14");
    expect(html).toContain("slope = 1.000");
  });

  it("anti-calibrated: still renders the diagram honestly, no crash", async () => {
    const rows = [...repeatRows(0.9, "NO", 20), ...repeatRows(0.1, "YES", 20)];
    const curve = [
      bin(0.0, 0.2, 12, 0.1, 0.9, [0.75, 0.99]),
      bin(0.4, 0.6, 16, 0.5, 0.5, [0.34, 0.66]),
      bin(0.8, 1.0, 12, 0.9, 0.1, [0.01, 0.25]),
    ];
    const manifest = manifestFromRows(rows, {
      calibrationCurve: curve,
      calibrationSlope: { slope: -1.0, ciLow: -1.3, ciHigh: -0.7, sampleSize: 40 },
    });
    const html = await renderPage(manifest);
    expect(html).toContain("Reliability diagram");
    expect(html).toContain("slope = -1.000");
    expect(html).toContain("n=12");
    // A bad firm is still scored against the same comparators.
    expect(html).toContain("What this means");
  });

  it("partial resolution index is disclosed, not hidden", async () => {
    const rows = repeatRows(0.6, "YES", 30);
    const manifest = manifestFromRows(rows, { resolvedIndexComplete: false });
    const html = await renderPage(manifest);
    expect(html).toContain("Partial index");
  });

  it("slice filter always surfaces the selected slice's sample size", async () => {
    const rows = repeatRows(0.6, "YES", 7);
    const manifest = manifestFromRows(rows, {
      domains: ["geopolitics", "economics"],
      venues: [
        { key: "Polymarket", label: "Polymarket", n: 4 },
        { key: "Kalshi", label: "Kalshi", n: 3 },
      ],
      filter: {
        domain: "geopolitics",
        methodName: null,
        methodVersion: null,
        venue: null,
        horizon: null,
      },
    });
    const html = await renderPage(manifest, { domain: "geopolitics" });
    expect(html).toContain("selected slice");
    expect(html).toContain("n=7 resolved");
  });
});

// ── Component-level guarantees ────────────────────────────────────────────

describe("CalibrationComparators", () => {
  it("anchors random and always-50% at 0.25 and withholds an unstable firm number", () => {
    const headline = makeHeadlineBrier(0.18, 5, { ciLow: 0.1, ciHigh: 0.25 });
    const html = renderToStaticMarkup(
      <CalibrationComparators headline={headline} outcomeBaseRate={0.4} />,
    );
    expect(html).toContain("Random guessing");
    expect(html).toContain("Brier 0.250");
    // climatology = 0.4 * 0.6 = 0.24
    expect(html).toContain("Brier 0.240");
    expect(html).toContain("Withheld");
  });

  it("shows the firm Brier when the headline is stable", () => {
    const headline = makeHeadlineBrier(0.18, 120, { ciLow: 0.15, ciHigh: 0.21 });
    const html = renderToStaticMarkup(
      <CalibrationComparators headline={headline} outcomeBaseRate={0.5} />,
    );
    expect(html).toContain("Brier 0.180");
  });
});

describe("CalibrationPlot", () => {
  it("draws the diagonal, labels bins by n, and greys sparse bins", () => {
    const bins = [
      bin(0.0, 0.2, 12, 0.1, 0.12, [0.03, 0.22]),
      bin(0.8, 1.0, 3, 0.9, 0.66, null), // sparse
    ];
    const html = renderToStaticMarkup(<CalibrationPlot bins={bins} />);
    // Diagonal reference.
    expect(html).toContain("#d4a017");
    expect(html).toContain("perfect calibration");
    // Both bins labelled by sample size.
    expect(html).toContain("n=12");
    expect(html).toContain("n=3");
    // Sparse bin uses the grey marker colour.
    expect(html).toContain("#a39a86");
  });

  it("renders an honest empty state with no bins", () => {
    const html = renderToStaticMarkup(<CalibrationPlot bins={[]} />);
    expect(html).toContain("No resolved forecasts yet");
  });
});

describe("CalibrationSliceFilter", () => {
  it("renders chips for every facet and links toggle query params", () => {
    const manifest = mkManifest({
      counts: {
        total: 12,
        resolvedBinary: 12,
        withdrawn: 0,
        staleUnresolved: 0,
        continuous: 0,
      },
      domains: ["geopolitics"],
      methods: [{ name: "edge_calc", version: "1", n: 12 }],
      venues: [{ key: "Polymarket", label: "Polymarket", n: 12 }],
      horizons: [{ key: "8-30", label: "8–30 days", n: 12 }],
    });
    const html = renderToStaticMarkup(
      <CalibrationSliceFilter
        manifest={manifest}
        active={{
          domain: null,
          methodName: null,
          methodVersion: null,
          venue: null,
          horizon: null,
        }}
      />,
    );
    expect(html).toContain("Domain");
    expect(html).toContain("Source method");
    expect(html).toContain("Market venue");
    expect(html).toContain("Resolution time horizon");
    expect(html).toContain("geopolitics");
    expect(html).toContain("venue=Polymarket");
    expect(html).toContain("horizon=8-30");
    expect(html).toContain("n=12 resolved");
  });
});
