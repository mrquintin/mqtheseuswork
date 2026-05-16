import React, { type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PublishedConclusion } from "@/lib/conclusionsRead";

type ElementNode = ReactElement<{
  [key: string]: unknown;
  children?: ReactNode;
  onClick?: () => void;
}>;

function conclusion(overrides: Partial<PublishedConclusion> = {}): PublishedConclusion {
  return {
    id: "pub-1",
    kind: "CONCLUSION",
    slug: "focused-article-title",
    version: 2,
    sourceConclusionId: "conclusion-1",
    publishedAt: "2026-05-01T12:00:00.000Z",
    doi: "",
    zenodoRecordId: "",
    discountedConfidence: 0.7,
    statedConfidence: 0.74,
    calibrationDiscountReason: "",
    payload: {
      schema: "theseus.publicConclusion.v1",
      conclusionText: "A focused article title",
      rationale: "",
      topicHint: "",
      evidenceSummary: "",
      exitConditions: [],
      strongestObjection: { objection: "", firmAnswer: "" },
      openQuestionsAdjacent: [],
      voiceComparisons: [],
      methodology: {
        schema: "theseus.methodology.v1",
        reviewerNarrative: "",
        profiles: [],
      },
      timeline: [],
      whatWouldChangeOurMind: [],
      citations: [],
    },
    ...overrides,
  };
}

function flattenChildren(children: ReactNode): ReactNode[] {
  if (children === null || children === undefined || children === false) return [];
  if (Array.isArray(children)) return children.flatMap(flattenChildren);
  return [children];
}

function isElement(node: ReactNode): node is ElementNode {
  return (
    typeof node === "object" &&
    node !== null &&
    "props" in (node as object) &&
    "type" in (node as object)
  );
}

function findElement(
  root: ReactNode,
  predicate: (node: ElementNode) => boolean,
): ElementNode | null {
  const stack = flattenChildren(root);
  while (stack.length) {
    const node = stack.shift();
    if (!isElement(node)) continue;
    if (predicate(node)) return node;
    stack.unshift(...flattenChildren(node.props.children));
  }
  return null;
}

describe("RespondCallout", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.doUnmock("react");
    vi.resetModules();
  });

  it("renders a default-collapsed scoped form without the conclusion selector", async () => {
    const { default: RespondCallout } = await import("@/components/RespondCallout");

    const html = renderToStaticMarkup(<RespondCallout conclusions={[conclusion()]} />);

    expect(html).toContain("<details");
    expect(html).not.toContain("<details open");
    expect(html).toContain("Submit a structured response");
    expect(html).toContain("Responding to: &#x27;A focused article title&#x27;");
    expect(html).not.toContain("Conclusion revision (published row id)");
    expect(html).not.toContain("focused-article-title v2 - 2026-05-01");
    expect(html).toContain("Response type");
  });

  it("renders the listing selector when multiple conclusions are available", async () => {
    const { default: RespondCallout } = await import("@/components/RespondCallout");

    const html = renderToStaticMarkup(
      <RespondCallout
        conclusions={[
          conclusion(),
          conclusion({
            id: "pub-2",
            slug: "second-publication",
            version: 1,
            payload: {
              ...conclusion().payload,
              conclusionText: "A second public title",
            },
          }),
        ]}
      />,
    );

    expect(html).toContain("Conclusion revision (published row id)");
    expect(html).toContain("<select");
    expect(html).toContain("focused-article-title v2 - 2026-05-01");
    expect(html).toContain("second-publication v1 - 2026-05-01");
    expect(html).not.toContain("Responding to:");
  });

  it("keeps RespondForm submitting to the public responses endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const stateValues = [
      "pub-1",
      "counter_evidence",
      "This response body is long enough to pass validation.",
      "reader@example.com",
      "0000-0002-1825-0097",
      "https://example.com/source",
      false,
      null,
      false,
    ];
    let stateIndex = 0;

    vi.doMock("react", async () => {
      const actual = await vi.importActual<typeof import("react")>("react");
      return {
        ...actual,
        useState: vi.fn((initial: unknown) => {
          const value = stateValues[stateIndex] ?? initial;
          stateIndex += 1;
          return [value, vi.fn()];
        }),
      };
    });

    const { default: RespondForm } = await import("@/components/RespondForm");
    const tree = RespondForm({ conclusions: [conclusion()] }) as ElementNode;
    const button = findElement(tree, (node) => node.type === "button");

    expect(button).not.toBeNull();
    button?.props.onClick?.();

    expect(fetchMock).toHaveBeenCalledWith("/api/public/responses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        publishedConclusionId: "pub-1",
        kind: "counter_evidence",
        body: "This response body is long enough to pass validation.",
        citationUrl: "https://example.com/source",
        submitterEmail: "reader@example.com",
        orcid: "0000-0002-1825-0097",
        pseudonymous: false,
        publishConsent: false,
      }),
    });
  });
});
