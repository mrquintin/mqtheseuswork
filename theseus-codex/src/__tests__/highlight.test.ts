import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { highlightSubstring } from "@/lib/highlight";

describe("highlightSubstring", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("wraps the verbatim substring in a mark element", () => {
    const html = renderToStaticMarkup(
      highlightSubstring("The durable compounding claim holds.", "durable compounding"),
    );

    expect(html).toContain("<mark");
    expect(html).toContain(">durable compounding</mark>");
    expect(html).toContain("The ");
    expect(html).toContain(" claim holds.");
  });

  it("falls back to plain text when the substring is absent", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const html = renderToStaticMarkup(
      highlightSubstring("The source text is intact.", "fabricated quote"),
    );

    expect(html).toBe("The source text is intact.");
    expect(warn).toHaveBeenCalledWith(
      "highlightSubstring: span is not a substring of text",
    );
  });
});
