import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PublicAskResponse } from "@/lib/publicAsk";

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
    // useState calls in declaration order:
    //  1. query    (string)
    //  2. pending  (boolean)
    //  3. error    (string | null)
    //  4. response (PublicAskResponse | null)
    //  5. activeIdx (number)
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

  it("renders top conclusion + open question with methodology and confidence pills", async () => {
    const response: PublicAskResponse = {
      query: "land value capture",
      results: {
        conclusion: [
          {
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
          },
        ],
        article: [],
        opinion: [],
        open_question: [
          {
            id: "oq-1",
            kind: "open_question",
            title: "Does land value capture work in low-density cities?",
            href: "/methodology/open-questions#q-oq-1",
            snippet:
              "Whether the mechanism still pays for infrastructure in low-density cities is unresolved.",
            relevance: 0.61,
            confidence: null,
            methodology: null,
            topicHint: "urban-economics",
            occurredAt: "2026-03-12T00:00:00.000Z",
          },
        ],
      },
      topScore: 0.84,
      noResult: false,
      closestOpenQuestion: null,
      suggestedRephrasings: [],
      queryBucket: "abcdef012345",
    };

    withResponseState(response);
    const { default: ReloadedBox } = await import("@/components/PublicAskBox");
    const html = renderToStaticMarkup(
      <ReloadedBox mode="full" initialQuery="land value capture" />,
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
  });

  it("fires the no-result fallback and surfaces the closest open question", async () => {
    const response: PublicAskResponse = {
      query: "favorite octopus aquarium",
      results: {
        conclusion: [],
        article: [],
        opinion: [],
        open_question: [],
      },
      topScore: 0.04,
      noResult: true,
      closestOpenQuestion: {
        id: "oq-2",
        kind: "open_question",
        title: "When do wage-price spirals decouple from money supply?",
        href: "/methodology/open-questions#q-oq-2",
        snippet: "The conditions under which they become self-sustaining remain open.",
        relevance: 0.0,
        confidence: null,
        methodology: null,
        topicHint: null,
        occurredAt: "2026-02-01T00:00:00.000Z",
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
    expect(html.toLowerCase()).toContain("closest open question");
    expect(html).toContain("When do wage-price spirals decouple from money supply?");
    expect(html).not.toContain('data-testid="public-ask-results"');
  });

  it("renders suggested rephrasings when the response is borderline", async () => {
    const response: PublicAskResponse = {
      query: "value capture",
      results: {
        conclusion: [
          {
            id: "pub-c1",
            kind: "conclusion",
            title: "Land value capture funds infrastructure",
            href: "/c/land-value-capture",
            snippet: "Capturing land value uplift around new transit pays for the transit itself.",
            relevance: 0.30,
            confidence: 0.62,
            methodology: "six_layer_coherence",
            topicHint: null,
            occurredAt: "2026-04-01T00:00:00.000Z",
          },
        ],
        article: [],
        opinion: [],
        open_question: [],
      },
      topScore: 0.22,
      noResult: false,
      closestOpenQuestion: null,
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
