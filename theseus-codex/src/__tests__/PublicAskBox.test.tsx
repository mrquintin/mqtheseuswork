import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PublicAskResponse, PublicAskResult } from "@/lib/publicAsk";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

import PublicAskBox from "@/components/PublicAskBox";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.doUnmock("react");
  vi.resetModules();
});

describe("PublicAskBox — SSR shell", () => {
  it("renders an empty ask box with input + slash hint", () => {
    const html = renderToStaticMarkup(<PublicAskBox mode="compact" />);
    expect(html).toContain('data-testid="public-ask-box"');
    expect(html).toContain('data-testid="public-ask-input"');
    expect(html).toContain('data-testid="public-ask-submit"');
    expect(html).toContain("ASK THE FIRM");
    expect(html).toContain("<kbd>/</kbd>");
  });

  it("does not pre-render any results in compact mode", () => {
    const html = renderToStaticMarkup(
      <PublicAskBox mode="compact" initialQuery="land value capture" />,
    );
    expect(html).not.toContain('data-testid="public-ask-results"');
    expect(html).not.toContain('data-testid="public-ask-no-result"');
  });
});

describe("PublicAskBox — full-mode results render", () => {
  function withResponseState(response: PublicAskResponse | null) {
    // useState calls in declaration order for PublicAskBox:
    //  1. query    (string)
    //  2. pending  (boolean)
    //  3. error    (string | null)
    //  4. response (PublicAskResponse | null)
    //  5. activeIdx (number)
    // Nested components (NoResultPanel's ResearchSuggestionForm) call
    // useState after these five; the mock returns their `initial` for
    // every call past index 4, which is exactly the idle render we want.
    const stateValues: unknown[] = [
      response?.query ?? "",
      false,
      null,
      response,
      -1,
    ];
    let i = 0;
    vi.doMock("react", async () => {
      const actual = await vi.importActual<typeof import("react")>("react");
      return {
        ...actual,
        useState: vi.fn((initial: unknown) => {
          const value = i < stateValues.length ? stateValues[i] : initial;
          i += 1;
          return [value, vi.fn()];
        }),
        // useEffect must not run during SSR test rendering anyway,
        // but stubbing it as a no-op makes the test independent of
        // any environment differences.
        useEffect: vi.fn(),
      };
    });
  }

  const RESULT_BASE: Omit<PublicAskResult, "id" | "kind" | "title" | "href"> = {
    snippet: "",
    relevance: 0.5,
    confidence: null,
    methodology: null,
    topicHint: null,
    occurredAt: "2026-04-01T00:00:00.000Z",
    isCurrent: true,
  };

  it("renders the query-class badge and top conclusion with methodology, confidence, and freshness pills", async () => {
    const response: PublicAskResponse = {
      query: "what does the firm think about land value capture",
      queryClass: "factual-claim",
      results: {
        conclusion: [
          {
            ...RESULT_BASE,
            id: "pub-c1",
            kind: "conclusion",
            title: "Land value capture funds infrastructure",
            href: "/c/land-value-capture",
            snippet:
              "Capturing land value uplift around new transit pays for the transit itself.",
            relevance: 0.84,
            confidence: 0.72,
            methodology: "six_layer_coherence",
            topicHint: "urban-economics",
            occurredAt: "2026-04-01T00:00:00.000Z",
            isCurrent: true,
          },
        ],
        article: [],
        opinion: [],
        open_question: [
          {
            ...RESULT_BASE,
            id: "oq-1",
            kind: "open_question",
            title: "Does land value capture work in low-density cities?",
            href: "/methodology/open-questions#q-oq-1",
            snippet:
              "Whether the mechanism still pays for infrastructure in low-density cities is unresolved.",
            relevance: 0.61,
            occurredAt: "2020-03-12T00:00:00.000Z",
            isCurrent: false,
          },
        ],
      },
      topScore: 0.84,
      noResult: false,
      closestOpenQuestion: null,
      closestRelatedConclusion: null,
      suggestedRephrasings: [],
      queryBucket: "abcdef012345",
    };

    withResponseState(response);
    const { default: ReloadedBox } = await import("@/components/PublicAskBox");
    const html = renderToStaticMarkup(
      <ReloadedBox mode="full" initialQuery={response.query} />,
    );

    expect(html).toContain('data-testid="public-ask-results"');
    expect(html).toContain("Land value capture funds infrastructure");
    expect(html).toContain("Does land value capture work in low-density cities?");
    expect(html).toContain('data-testid="public-ask-rail-conclusion"');
    expect(html).toContain('data-testid="public-ask-rail-open_question"');
    expect(html).toContain('data-testid="public-ask-methodology-pill"');
    expect(html).toContain("METHOD · six_layer_coherence");
    expect(html).toContain('data-testid="public-ask-confidence-pill"');
    expect(html).toContain("CONFIDENCE · 72%");
    expect(html).toContain(
      "Capturing land value uplift around new transit pays for the transit itself.",
    );

    // Query-class badge surfaces the routing decision.
    expect(html).toContain('data-testid="public-ask-query-class"');
    expect(html).toContain('data-query-class="factual-claim"');
    expect(html).toContain("FACTUAL CLAIM");

    // Freshness pill: a current result and a stale one are both shown,
    // each labelled — staleness is surfaced, never silently de-ranked.
    expect(html).toContain('data-testid="public-ask-freshness-pill"');
    expect(html).toContain("STILL CURRENT");
    expect(html).toContain("STALE");
    expect(html).toContain('data-current="false"');
    expect(html).toContain("2026-04-01");
  });

  it("orders rails by query class — a methodology question leads with articles", async () => {
    const response: PublicAskResponse = {
      query: "how did you derive the land value capture conclusion",
      queryClass: "methodology-question",
      results: {
        conclusion: [
          {
            ...RESULT_BASE,
            id: "c1",
            kind: "conclusion",
            title: "Land value capture funds infrastructure",
            href: "/c/lvc",
          },
        ],
        article: [
          {
            ...RESULT_BASE,
            id: "a1",
            kind: "article",
            title: "How the firm derives funding conclusions",
            href: "/a/method",
          },
        ],
        opinion: [],
        open_question: [],
      },
      topScore: 0.7,
      noResult: false,
      closestOpenQuestion: null,
      closestRelatedConclusion: null,
      suggestedRephrasings: [],
      queryBucket: "111111111111",
    };

    withResponseState(response);
    const { default: ReloadedBox } = await import("@/components/PublicAskBox");
    const html = renderToStaticMarkup(
      <ReloadedBox mode="full" initialQuery={response.query} />,
    );

    expect(html).toContain('data-query-class="methodology-question"');
    // The article rail is rendered before the conclusion rail for this class.
    const articleIdx = html.indexOf('data-testid="public-ask-rail-article"');
    const conclusionIdx = html.indexOf('data-testid="public-ask-rail-conclusion"');
    expect(articleIdx).toBeGreaterThan(-1);
    expect(conclusionIdx).toBeGreaterThan(-1);
    expect(articleIdx).toBeLessThan(conclusionIdx);
  });

  it("fires the enriched no-result fallback: closest open question, closest conclusion, and suggestion form", async () => {
    const response: PublicAskResponse = {
      query: "favorite octopus aquarium",
      queryClass: "browse",
      results: {
        conclusion: [],
        article: [],
        opinion: [],
        open_question: [],
      },
      topScore: 0.04,
      noResult: true,
      closestOpenQuestion: {
        ...RESULT_BASE,
        id: "oq-2",
        kind: "open_question",
        title: "When do wage-price spirals decouple from money supply?",
        href: "/methodology/open-questions#q-oq-2",
        snippet: "The conditions under which they become self-sustaining remain open.",
        relevance: 0.0,
        occurredAt: "2026-02-01T00:00:00.000Z",
        isCurrent: true,
      },
      closestRelatedConclusion: {
        ...RESULT_BASE,
        id: "c-9",
        kind: "conclusion",
        title: "Inflation is a monetary phenomenon",
        href: "/c/inflation-monetary",
        snippet: "Inflation in the long run is driven by money supply growth.",
        relevance: 0.0,
        occurredAt: "2026-01-15T00:00:00.000Z",
        isCurrent: true,
      },
      suggestedRephrasings: [],
      queryBucket: "0123456789ab",
    };

    withResponseState(response);
    const { default: ReloadedBox } = await import("@/components/PublicAskBox");
    const html = renderToStaticMarkup(
      <ReloadedBox mode="full" initialQuery="favorite octopus aquarium" />,
    );

    expect(html).toContain('data-testid="public-ask-no-result"');
    expect(html.toLowerCase()).toContain("the firm has not addressed this directly");

    // Both pointers are surfaced.
    expect(html).toContain('data-testid="public-ask-closest-open-question"');
    expect(html).toContain("When do wage-price spirals decouple from money supply?");
    expect(html).toContain('data-testid="public-ask-closest-conclusion"');
    expect(html).toContain("Inflation is a monetary phenomenon");

    // The research-suggestion form makes the miss actionable.
    expect(html).toContain('data-testid="public-ask-suggestion-form"');
    expect(html).toContain('data-testid="public-ask-suggestion-title"');
    expect(html.toLowerCase()).toContain("submit a research suggestion");

    expect(html).not.toContain('data-testid="public-ask-results"');
  });

  it("renders suggested rephrasings when the response is borderline", async () => {
    const response: PublicAskResponse = {
      query: "value capture",
      queryClass: "browse",
      results: {
        conclusion: [
          {
            ...RESULT_BASE,
            id: "pub-c1",
            kind: "conclusion",
            title: "Land value capture funds infrastructure",
            href: "/c/land-value-capture",
            snippet: "Capturing land value uplift around new transit pays for the transit itself.",
            relevance: 0.3,
            confidence: 0.62,
            methodology: "six_layer_coherence",
          },
        ],
        article: [],
        opinion: [],
        open_question: [],
      },
      topScore: 0.22,
      noResult: false,
      closestOpenQuestion: null,
      closestRelatedConclusion: null,
      suggestedRephrasings: [
        "Does land value capture work in low-density cities?",
        "Property tax base expansion follows transit",
      ],
      queryBucket: "ffeeddccbbaa",
    };

    withResponseState(response);
    const { default: ReloadedBox } = await import("@/components/PublicAskBox");
    const html = renderToStaticMarkup(
      <ReloadedBox mode="full" initialQuery="value capture" />,
    );

    expect(html).toContain('data-testid="public-ask-rephrasings"');
    expect(html.toLowerCase()).toContain("did you mean");
    expect(html).toContain("Does land value capture work in low-density cities?");
    expect(html).toContain("Property tax base expansion follows transit");
  });
});
