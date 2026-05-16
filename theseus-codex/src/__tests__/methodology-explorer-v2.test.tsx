import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Methodology Explorer v2 (Round 17 prompt 07 refinement).
 *
 * Covers the three things the refinement is judged on:
 *   - the landing page presents the meta-method / catalog / empirical
 *     record as three ordered layers, with the meta-method never below
 *     the catalog (snapshot + ordering assertions);
 *   - every cross-link on a method page is reachable in one click, and
 *     in plain server-rendered HTML so a no-JavaScript reader can follow
 *     it (navigation assertions);
 *   - focus order walks the new hierarchy top-to-bottom (accessibility
 *     assertion on source order, which is tab order for static flow).
 */

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
  notFound: vi.fn(),
}));

vi.mock("@/components/PublicHeader", () => ({
  default: ({ authed }: { authed: boolean }) => (
    <header data-authed={String(authed)}>Public header</header>
  ),
}));

vi.mock("@/components/SubscribeForm", () => ({
  default: ({ title }: { title: string }) => (
    <div data-subscribe-form>{title}</div>
  ),
}));

vi.mock("@/lib/auth", () => ({
  getFounder: vi.fn().mockResolvedValue(null),
}));

const {
  buildMethodologyManifest,
  getCatalog,
  publicModesForMethod,
  queryRaw,
  resolvePublicOrganizationId,
  loadPublicOpenQuestions,
  listPublicPrinciples,
} = vi.hoisted(() => ({
  buildMethodologyManifest: vi.fn(),
  getCatalog: vi.fn(),
  publicModesForMethod: vi.fn(),
  queryRaw: vi.fn(),
  resolvePublicOrganizationId: vi.fn(),
  loadPublicOpenQuestions: vi.fn(),
  listPublicPrinciples: vi.fn(),
}));

vi.mock("@/lib/methodologyManifest", () => ({
  buildMethodologyManifest,
  driftLabel: (s: string) =>
    s === "escalate" ? "Drifting" : s === "warn" ? "Watch" : "OK",
  driftColor: (s: string) =>
    s === "escalate" ? "#c0392b" : s === "warn" ? "#d4a017" : "#888",
}));

vi.mock("@/lib/failureModes", () => ({
  getCatalog,
  publicModesForMethod,
}));

vi.mock("@/lib/db", () => ({
  db: {
    get $queryRaw() {
      return queryRaw;
    },
    methodologyReviewWeek: {
      findFirst: vi.fn().mockResolvedValue(null),
    },
  },
}));

vi.mock("@prisma/client", () => ({
  Prisma: {
    sql: (strings: TemplateStringsArray, ...values: unknown[]) => ({
      strings,
      values,
    }),
    join: (values: unknown[]) => ({ values }),
  },
}));

vi.mock("@/lib/conclusionsRead", () => ({
  resolvePublicOrganizationId,
}));

vi.mock("@/lib/openQuestionsApi", () => ({
  loadPublicOpenQuestions,
}));

vi.mock("@/lib/principlesApi", () => ({
  listPublicPrinciples,
}));

import MethodologyPage from "@/app/methodology/page";
import MethodPage from "@/app/methodology/[method]/page";
import MethodCrossLinks, { ReaderTrail } from "@/components/MethodCrossLinks";

function manifestFixture() {
  return {
    v: 1,
    schema: "theseus.methodology.manifest" as const,
    generatedAt: "2026-05-01T00:00:00.000Z",
    methods: [
      {
        name: "coherence_judge",
        version: "1.2.0",
        description: "Judges whether a set of claims hangs together.",
        status: "active",
        depth: 1,
        domain: "epistemics",
        conclusionsProduced: 12,
        calibration: {
          slope: 1.0341,
          ciLow: 0.8123,
          ciHigh: 1.2604,
          sampleSize: 40,
          domain: "epistemics",
          weightedBrier: 0.1423,
          severityPassRate: 0.6612,
        },
        drift: { state: "ok" as const, lastActiveAt: null },
        publicFailureModeCount: 1,
        lastReviewDate: "2026-04-01T00:00:00.000Z",
      },
      {
        name: "claim_extractor",
        version: "2.0.0",
        description: "Pulls discrete checkable claims out of source text.",
        status: "deprecated",
        depth: 0,
        domain: null,
        conclusionsProduced: 3,
        calibration: null,
        drift: { state: "warn" as const, lastActiveAt: "2026-03-10T00:00:00.000Z" },
        publicFailureModeCount: 0,
        lastReviewDate: null,
      },
    ],
    edges: [
      { src: "coherence_judge", dst: "claim_extractor" },
      { src: "synthesis", dst: "coherence_judge" },
    ],
    publicFailureModes: [
      {
        method: "coherence_judge",
        name: "circular-support",
        severity: "medium",
        description: "Claims that only support each other.",
        trigger: "tight clusters",
        mitigation: "external anchor",
      },
    ],
    publicTrackRecords: [],
  };
}

function configureMethodPageMocks() {
  buildMethodologyManifest.mockResolvedValue(manifestFixture());
  getCatalog.mockReturnValue({
    method: "coherence_judge",
    failures: "ok",
    modes: [{ name: "circular-support" }, { name: "anchor-drift" }],
  });
  publicModesForMethod.mockReturnValue([{ name: "circular-support" }]);
  resolvePublicOrganizationId.mockResolvedValue("org-1");
  queryRaw.mockResolvedValue([{ conclusionId: "c1" }]);
  loadPublicOpenQuestions.mockResolvedValue([
    {
      id: "oq1",
      summary: "Does coherence transfer cross-domain?",
      createdAt: new Date("2026-02-01T00:00:00.000Z"),
      domain: "epistemics",
      candidateMethodNames: ["coherence_judge"],
      gatedPublishedConclusionIds: [],
    },
    {
      id: "oq2",
      summary: "Unrelated question about another method.",
      createdAt: new Date("2026-02-02T00:00:00.000Z"),
      domain: "markets",
      candidateMethodNames: ["some_other_method"],
      gatedPublishedConclusionIds: [],
    },
  ]);
  listPublicPrinciples.mockResolvedValue([
    {
      id: "p1",
      text: "Coherence is necessary but not sufficient for truth.",
      domains: ["epistemics"],
      clusterConclusionIds: ["c1", "c9"],
      citedConclusionIds: [],
      status: "accepted",
      convictionScore: 0.71,
      underlyingConclusions: [],
    },
    {
      id: "p2",
      text: "A principle from an unrelated cluster.",
      domains: ["markets"],
      clusterConclusionIds: ["c42"],
      citedConclusionIds: [],
      status: "accepted",
      convictionScore: 0.6,
      underlyingConclusions: [],
    },
  ]);
}

async function renderMethodologyPage(): Promise<string> {
  buildMethodologyManifest.mockResolvedValue(manifestFixture());
  const element = await MethodologyPage();
  return renderToStaticMarkup(element);
}

async function renderMethodPage(method = "coherence_judge"): Promise<string> {
  configureMethodPageMocks();
  const element = await MethodPage({
    params: Promise.resolve({ method }),
  });
  return renderToStaticMarkup(element);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Methodology landing — information hierarchy", () => {
  it("snapshots the three-layer landing page", async () => {
    const html = await renderMethodologyPage();
    expect(html).toMatchSnapshot();
  });

  it("orders the layers meta-method → catalog → empirical record", async () => {
    const html = await renderMethodologyPage();

    const metaMethod = html.indexOf('id="methodology-meta-method"');
    const catalog = html.indexOf('id="methodology-index"');
    const empirical = html.indexOf('id="methodology-empirical-record"');

    expect(metaMethod).toBeGreaterThan(-1);
    expect(catalog).toBeGreaterThan(-1);
    expect(empirical).toBeGreaterThan(-1);

    // Layer 1 is never buried below the catalog.
    expect(metaMethod).toBeLessThan(catalog);
    expect(catalog).toBeLessThan(empirical);

    // The headings read in the same order.
    expect(html.indexOf("The meta-method")).toBeLessThan(
      html.indexOf("The methods catalog"),
    );
    expect(html.indexOf("The methods catalog")).toBeLessThan(
      html.indexOf("Benchmarks, calibration"),
    );
  });

  it("keeps all three layers reachable in server-rendered HTML", async () => {
    const html = await renderMethodologyPage();
    // Layer 1 surfaces.
    expect(html).toContain('href="/methodology/criteria"');
    expect(html).toContain('href="/methodology/composition"');
    expect(html).toContain('href="/methodology/principles"');
    // Layer 2 catalog content is in the HTML, not behind hydration.
    expect(html).toContain("coherence_judge");
    expect(html).toContain("claim_extractor");
    // Layer 3 empirical record.
    expect(html).toContain('href="/methodology/benchmark/qh"');
    expect(html).toContain('href="/methodology/redteam"');
    expect(html).toContain('href="/methodology/replicate"');
  });
});

describe("Methodology landing — focus order through the hierarchy", () => {
  it("places the skip link first, then layer 1, catalog, layer 3 in tab order", async () => {
    const html = await renderMethodologyPage();

    // The skip link is the first focusable element on the page: the
    // first opening anchor tag in the document carries its class.
    const firstAnchor = html.indexOf("<a ");
    expect(firstAnchor).toBeGreaterThan(-1);
    expect(html.slice(firstAnchor, firstAnchor + 90)).toContain(
      "public-skip-link",
    );

    // Focusables then follow source order: a layer-1 link, then the
    // catalog's search field, then a layer-3 link.
    const layer1Link = html.indexOf('href="/methodology/criteria"');
    const catalogSearch = html.indexOf('type="search"');
    const layer3Link = html.indexOf('href="/methodology/redteam"');

    expect(firstAnchor).toBeLessThan(layer1Link);
    expect(layer1Link).toBeLessThan(catalogSearch);
    expect(catalogSearch).toBeLessThan(layer3Link);
  });

  it("rounds calibration slope to the precision the data supports", async () => {
    const html = await renderMethodologyPage();
    // Fixture slope is 1.0341 — the explorer never renders raw float width.
    expect(html).toContain("1.03");
    expect(html).not.toContain("1.0341");
    expect(html).not.toContain("0.8123");
  });
});

describe("Method page — reorganized layout", () => {
  it("snapshots the reorganized method page", async () => {
    const html = await renderMethodPage();
    expect(html).toMatchSnapshot();
  });

  it("front-loads the one-line description and the three essentials pills", async () => {
    const html = await renderMethodPage();

    const description = html.indexOf(
      "Judges whether a set of claims hangs together.",
    );
    const whatWeTested = html.indexOf('href="/methodology/benchmark/qh"');
    const trackRecord = html.indexOf(
      'href="/methodology/coherence_judge/track-record"',
    );
    const howToChallenge = html.indexOf('href="/critiques"');

    expect(description).toBeGreaterThan(-1);
    expect(whatWeTested).toBeGreaterThan(-1);
    expect(trackRecord).toBeGreaterThan(-1);
    expect(howToChallenge).toBeGreaterThan(-1);

    // Description and pills come before the now-secondary tab strip.
    const detailedSections = html.indexOf("Detailed sections");
    expect(description).toBeLessThan(detailedSections);
    expect(whatWeTested).toBeLessThan(detailedSections);
    expect(trackRecord).toBeLessThan(detailedSections);
    expect(howToChallenge).toBeLessThan(detailedSections);
  });

  it("rounds the slope shown in the track-record pill", async () => {
    const html = await renderMethodPage();
    expect(html).toContain("Calibration slope 1.03");
    expect(html).not.toContain("1.0341");
  });

  it("demotes the tab strip from an ARIA tablist to a navigation landmark", async () => {
    const html = await renderMethodPage();
    expect(html).not.toContain('role="tablist"');
    expect(html).not.toContain('role="tab"');
    expect(html).toContain("Detailed sections for method coherence_judge");
  });
});

describe("Method page — cross-link density", () => {
  it("reaches composed methods, dependents, open questions, and principles in one click", async () => {
    const html = await renderMethodPage();

    // Methods this one composes (manifest edge src === method).
    expect(html).toContain('href="/methodology/claim_extractor"');
    // Methods that depend on this one (manifest edge dst === method).
    expect(html).toContain('href="/methodology/synthesis"');
    // Open questions tied to this method.
    expect(html).toContain('href="/methodology/open-questions"');
    expect(html).toContain("Does coherence transfer cross-domain?");
    // Principles its evidence produced.
    expect(html).toContain('href="/methodology/principles"');
    expect(html).toContain(
      "Coherence is necessary but not sufficient for truth.",
    );
  });

  it("filters out open questions and principles tied to other methods", async () => {
    const html = await renderMethodPage();
    expect(html).not.toContain("Unrelated question about another method.");
    expect(html).not.toContain("A principle from an unrelated cluster.");
  });

  it("degrades to empty cross-link groups when the database is unavailable", async () => {
    configureMethodPageMocks();
    queryRaw.mockRejectedValue(new Error("db down"));
    loadPublicOpenQuestions.mockRejectedValue(new Error("db down"));

    const element = await MethodPage({
      params: Promise.resolve({ method: "coherence_judge" }),
    });
    const html = renderToStaticMarkup(element);

    // The page still renders, and the groups fall back to "None recorded."
    expect(html).toContain("How this method connects");
    expect(html).toContain("None recorded.");
  });
});

describe("MethodCrossLinks component — one-click reachability", () => {
  it("renders every relationship as a plain anchor", () => {
    const html = renderToStaticMarkup(
      <MethodCrossLinks
        method="coherence_judge"
        composes={["claim_extractor"]}
        dependedOnBy={["synthesis"]}
        openQuestions={[{ id: "oq1", summary: "An open question." }]}
        principles={[{ id: "p1", text: "A produced principle." }]}
      />,
    );

    expect(html).toContain('href="/methodology/claim_extractor"');
    expect(html).toContain('href="/methodology/synthesis"');
    expect(html).toContain('href="/methodology/open-questions"');
    expect(html).toContain('href="/methodology/principles"');
    expect(html).toContain("An open question.");
    expect(html).toContain("A produced principle.");
  });

  it("shows an explicit empty state instead of a missing group", () => {
    const html = renderToStaticMarkup(
      <MethodCrossLinks
        method="coherence_judge"
        composes={[]}
        dependedOnBy={[]}
        openQuestions={[]}
        principles={[]}
      />,
    );
    expect(html).toContain("Composes");
    expect(html).toContain("Depended on by");
    expect(html).toContain("Open questions");
    expect(html).toContain("Principles produced");
    expect(html).toContain("None recorded.");
  });
});

describe("ReaderTrail — progressive enhancement", () => {
  it("renders nothing without client-side state, so no-JS readers see no trail", () => {
    // renderToStaticMarkup runs no effects: the trail starts empty and
    // therefore produces no markup at all — it degrades, it never fails.
    expect(renderToStaticMarkup(<ReaderTrail />)).toBe("");
    expect(renderToStaticMarkup(<ReaderTrail current="coherence_judge" />)).toBe(
      "",
    );
  });
});
