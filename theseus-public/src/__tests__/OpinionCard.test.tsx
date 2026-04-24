// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

afterEach(() => {
  cleanup();
});
import { OpinionCard } from "@/app/currents/OpinionCard";
import { STANCE_LABEL } from "@/lib/stanceStyles";
import type { PublicCitation, PublicOpinion } from "@/lib/currentsTypes";

function makeCitation(i: number): PublicCitation {
  return {
    source_kind: i % 2 === 0 ? "conclusion" : "claim",
    source_id: `src-${i}-abcdef`,
    quoted_span: `span-${i}`,
    relevance_score: 0.5,
  };
}

function makeOpinion(overrides: Partial<PublicOpinion> = {}): PublicOpinion {
  return {
    id: "op-1",
    event_id: "evt-1",
    event_source_url: "https://x.example/status/1",
    event_author_handle: "someone",
    event_captured_at: "2026-04-20T00:00:00Z",
    topic_hint: "markets",
    stance: "agrees",
    confidence: 0.82,
    headline: "The firm sees a cascading rate cycle",
    body_markdown: "A short **paragraph** with an *inline* note.",
    uncertainty_notes: [],
    generated_at: "2026-04-20T11:59:30Z",
    citations: [makeCitation(1), makeCitation(2)],
    revoked: false,
    ...overrides,
  };
}

describe("OpinionCard", () => {
  it("renders the stance pill with the correct label", () => {
    const { getByTestId } = render(
      <OpinionCard op={makeOpinion({ stance: "disagrees" })} />,
    );
    const pill = getByTestId("stance-pill");
    expect(pill.textContent).toBe(STANCE_LABEL.disagrees);
  });

  it("renders the headline as text", () => {
    const { container } = render(<OpinionCard op={makeOpinion()} />);
    const h2 = container.querySelector("h2");
    expect(h2).not.toBeNull();
    expect(h2!.textContent).toBe("The firm sees a cascading rate cycle");
  });

  it("sanitizes markdown: <script> payload renders as text, not a script tag", () => {
    const hostile =
      "Before <script>alert(1)</script> after. And [link](javascript:alert(1))";
    const { container } = render(
      <OpinionCard op={makeOpinion({ body_markdown: hostile })} />,
    );
    // No script element ever ends up in the DOM.
    expect(container.querySelector("script")).toBeNull();
    // The literal "<script>" text is preserved as escaped text content.
    expect(container.textContent).toContain("<script>alert(1)</script>");
    // The javascript: URL is stripped — the rendered anchor href must not
    // carry the dangerous scheme.
    const anchors = Array.from(
      container.querySelectorAll("a"),
    ) as HTMLAnchorElement[];
    for (const a of anchors) {
      expect(a.getAttribute("href")?.startsWith("javascript:")).not.toBe(true);
    }
  });

  it("shows +N more when citations exceed 3", () => {
    const many = [1, 2, 3, 4, 5].map(makeCitation);
    const { getAllByTestId, getByTestId } = render(
      <OpinionCard op={makeOpinion({ citations: many })} />,
    );
    expect(getAllByTestId("citation-chip")).toHaveLength(3);
    expect(getByTestId("more-chips").textContent).toContain("+2 more");
  });

  it("omits the +N more badge when citations fit within the visible limit", () => {
    const { queryByTestId, getAllByTestId } = render(
      <OpinionCard
        op={makeOpinion({ citations: [makeCitation(1), makeCitation(2)] })}
      />,
    );
    expect(getAllByTestId("citation-chip")).toHaveLength(2);
    expect(queryByTestId("more-chips")).toBeNull();
  });

  it("links 'Ask a follow-up' to /currents/<id>#ask", () => {
    const { container } = render(
      <OpinionCard op={makeOpinion({ id: "op-xyz" })} />,
    );
    const anchors = Array.from(
      container.querySelectorAll("a"),
    ) as HTMLAnchorElement[];
    const ask = anchors.find((a) =>
      a.getAttribute("href")?.endsWith("#ask"),
    );
    expect(ask).toBeDefined();
    expect(ask!.getAttribute("href")).toBe("/currents/op-xyz#ask");
  });
});
