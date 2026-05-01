import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import AnswerMarkdown from "@/components/AnswerMarkdown";

describe("AnswerMarkdown", () => {
  it("renders bold markdown and turns resolved citations into links", () => {
    const html = renderToStaticMarkup(
      <AnswerMarkdown
        citations={{
          "[C:abc123]": {
            type: "conclusion",
            id: "abc123full",
            tier: "firm",
            url: "/conclusions/abc123full",
            preview: "Base-rate preview",
          },
          "[C:missing]": {
            type: "conclusion",
            id: "missing",
            tier: "unknown",
            url: null,
            preview: "",
          },
        }}
      >
        The firm holds **two** competing positions [C:abc123] and [C:missing].
      </AnswerMarkdown>,
    );

    expect(html).toContain("<strong");
    expect(html).toContain(">two</strong>");
    expect(html).toContain('href="/conclusions/abc123full"');
    expect(html).toContain('target="_blank"');
    expect(html).toContain('title="Base-rate preview"');
    expect(html).toMatch(/<a[^>]*><code[^>]*>\[C:abc123\]<\/code><\/a>/);
    expect(html).toMatch(/<span[^>]*>\[C:missing\]<\/span>/);
    expect(html).toContain("color:var(--ember)");
    expect(html).toContain(
      "Source not found in corpus — possible model hallucination",
    );
  });

  it("removes malicious script tags while preserving safe markdown", () => {
    const html = renderToStaticMarkup(
      <AnswerMarkdown>{"<script>alert(1)</script>**bold**"}</AnswerMarkdown>,
    );

    expect(html).not.toContain("<script");
    expect(html).not.toContain("alert(1)");
    expect(html).toContain("<strong");
    expect(html).toContain(">bold</strong>");
  });
});
