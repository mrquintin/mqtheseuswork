// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { SourceDrawer } from "@/app/currents/[id]/SourceDrawer";
import type { PublicCitation, PublicSource } from "@/lib/currentsTypes";

afterEach(() => {
  cleanup();
  // Reset the hash between tests so leftover state doesn't leak.
  if (typeof window !== "undefined") {
    window.history.replaceState(null, "", "/");
  }
});

let scrollSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  scrollSpy = vi.fn();
  // jsdom doesn't implement scrollIntoView; install a spy version.
  Element.prototype.scrollIntoView = scrollSpy as unknown as (
    arg?: boolean | ScrollIntoViewOptions,
  ) => void;
});

function citation(
  source_id: string,
  overrides: Partial<PublicCitation> = {},
): PublicCitation {
  return {
    source_kind: "conclusion",
    source_id,
    quoted_span: "quoted",
    relevance_score: 0.7,
    ...overrides,
  };
}

function source(
  source_id: string,
  overrides: Partial<PublicSource> = {},
): PublicSource {
  return {
    source_kind: "conclusion",
    source_id,
    full_text: "This is the full source text with a quoted region inside.",
    topic_hint: "markets",
    origin: "published",
    permalink: null,
    ...overrides,
  };
}

describe("SourceDrawer", () => {
  it("renders one SourceCard per citation when sources match", () => {
    const citations = [citation("src-a"), citation("src-b")];
    const sources = [source("src-a"), source("src-b")];
    const { getAllByTestId } = render(
      <SourceDrawer citations={citations} sources={sources} />,
    );
    expect(getAllByTestId("source-card")).toHaveLength(2);
  });

  it("renders the missing-source warning when a citation has no backing source", () => {
    const citations = [citation("src-present"), citation("src-absent")];
    const sources = [source("src-present")];
    const { getAllByTestId, getByTestId } = render(
      <SourceDrawer citations={citations} sources={sources} />,
    );
    expect(getAllByTestId("source-card")).toHaveLength(1);
    const missing = getByTestId("missing-source");
    expect(missing.textContent).toContain("src-absent");
  });

  it("scrolls to the targeted source on mount when the hash is #src-<id>", () => {
    window.history.replaceState(null, "", "/currents/op-1#src-src-b");
    const citations = [citation("src-a"), citation("src-b")];
    const sources = [source("src-a"), source("src-b")];
    render(<SourceDrawer citations={citations} sources={sources} />);
    expect(scrollSpy).toHaveBeenCalledTimes(1);
  });

  it("re-triggers scroll on a hashchange event", () => {
    const citations = [citation("src-a"), citation("src-b")];
    const sources = [source("src-a"), source("src-b")];
    render(<SourceDrawer citations={citations} sources={sources} />);
    expect(scrollSpy).not.toHaveBeenCalled();

    act(() => {
      window.history.replaceState(null, "", "/currents/op-1#src-src-a");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(scrollSpy).toHaveBeenCalledTimes(1);

    act(() => {
      window.history.replaceState(null, "", "/currents/op-1#src-src-b");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(scrollSpy).toHaveBeenCalledTimes(2);
  });

  it("flashes the active border on the targeted card", () => {
    window.history.replaceState(null, "", "/currents/op-1#src-src-a");
    const citations = [citation("src-a")];
    const sources = [source("src-a")];
    const { getByTestId } = render(
      <SourceDrawer citations={citations} sources={sources} />,
    );
    const card = getByTestId("source-card");
    expect(card.getAttribute("data-active")).toBe("true");
  });

  it("shows an empty-state message when there are no citations", () => {
    const { container } = render(
      <SourceDrawer citations={[]} sources={[]} />,
    );
    expect(container.textContent).toContain("Sources cited (0)");
    expect(container.textContent).toContain("did not cite any sources");
  });
});
