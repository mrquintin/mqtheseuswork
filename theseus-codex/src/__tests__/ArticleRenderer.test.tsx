import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import ArticleRenderer from "@/components/article/ArticleRenderer";

const FULL_FIXTURE = `# Real cost of growth. 8x, one argument.

The headline statistic looks defensible until you ask what it is
measuring. We have spent two quarters trying to pull the **8x**
number apart and the underlying argument turns out to be *one*
argument, not a cluster of independent claims.

## What the number measures

- It bundles capex, opex, and rebuild cost into a single multiplier.
- The denominator is *last cycle*, not *last comparable cycle*.
- The 8x is a point estimate; the confidence interval is wide.

## What the number does not measure

1. Capital recycled across business units.
2. Negative-cost rollups.
3. Throughput per dollar after the first integration cycle.

> A statistic that cannot say what its denominator is doing is not a
> statistic.

### The one argument

The real argument is: **growth is expensive only if you cannot reuse
what you already paid for**.

\`\`\`text
reuse rate ↑  →  effective growth cost ↓
\`\`\`

See the [methodology page](/methodology) and the
[external reference](https://example.com/growth).
`;

function render(body: string): string {
  return renderToStaticMarkup(<ArticleRenderer body={body} />);
}

describe("ArticleRenderer", () => {
  it("renders every supported markdown feature without dropping content", () => {
    const html = render(FULL_FIXTURE);

    // Headings: each level survives with its semantic tag.
    expect(html).toMatch(/<h1[^>]*>Real cost of growth\. 8x, one argument\.<\/h1>/);
    expect(html).toMatch(/<h2[^>]*>What the number measures<\/h2>/);
    expect(html).toMatch(/<h2[^>]*>What the number does not measure<\/h2>/);
    expect(html).toMatch(/<h3[^>]*>The one argument<\/h3>/);

    // Inline emphasis.
    expect(html).toMatch(/<strong[^>]*>8x<\/strong>/);
    expect(html).toMatch(/<em[^>]*>one<\/em>/);
    expect(html).toMatch(
      /<strong[^>]*>growth is expensive only if you cannot reuse\s+what you already paid for<\/strong>/,
    );

    // Lists: one <ul>, multiple <li>; one <ol>, multiple <li>.
    const ulMatches = html.match(/<ul[^>]*>/g) ?? [];
    expect(ulMatches.length).toBe(1);
    const olMatches = html.match(/<ol[^>]*>/g) ?? [];
    expect(olMatches.length).toBe(1);
    expect(html).toMatch(/<li[^>]*>It bundles capex, opex, and rebuild cost into a single multiplier\.<\/li>/);
    expect(html).toMatch(/<li[^>]*>Capital recycled across business units\.<\/li>/);

    // Blockquote.
    expect(html).toMatch(/<blockquote[^>]*>[\s\S]*statistic that cannot say what its denominator is doing[\s\S]*<\/blockquote>/);

    // Fenced code block.
    expect(html).toMatch(/<pre[^>]*>[\s\S]*reuse rate.*effective growth cost[\s\S]*<\/pre>/);

    // Links: internal stays internal, external opens in a new tab.
    expect(html).toContain('href="/methodology"');
    expect(html).toContain('href="https://example.com/growth"');
    expect(html).toMatch(/<a[^>]*href="https:\/\/example\.com\/growth"[^>]*target="_blank"/);

    // No literal markdown markers reach the rendered DOM.
    expect(html).not.toMatch(/<p[^>]*># /);
    expect(html).not.toMatch(/<p[^>]*>\* /);
    expect(html).not.toMatch(/<p[^>]*>- /);

    // The renderer never produces an inline error block on valid input.
    expect(html).not.toContain('data-testid="article-parse-error"');
  });

  it("preserves all three heading levels declared in the source", () => {
    const html = render(["# H1", "", "## H2", "", "### H3", "", "#### H4", "", "##### H5", "", "###### H6"].join("\n"));
    expect(html).toMatch(/<h1[^>]*>H1<\/h1>/);
    expect(html).toMatch(/<h2[^>]*>H2<\/h2>/);
    expect(html).toMatch(/<h3[^>]*>H3<\/h3>/);
    expect(html).toMatch(/<h4[^>]*>H4<\/h4>/);
    expect(html).toMatch(/<h5[^>]*>H5<\/h5>/);
    expect(html).toMatch(/<h6[^>]*>H6<\/h6>/);
  });

  it("renders tables (GFM) without dropping cells", () => {
    const md = [
      "| Term | Effect |",
      "| --- | --- |",
      "| reuse rate ↑ | cost ↓ |",
      "| reuse rate ↓ | cost ↑ |",
    ].join("\n");
    const html = render(md);
    expect(html).toContain("<table");
    expect(html).toMatch(/<th[^>]*>Term<\/th>/);
    expect(html).toMatch(/<td[^>]*>reuse rate ↑<\/td>/);
    expect(html).toMatch(/<td[^>]*>cost ↓<\/td>/);
  });

  it("survives MDX-style import/export lines without crashing", () => {
    // MDX bits aren't supported, but they should not bring down the
    // page — they fall through as literal-ish text rather than as a
    // sanitiser-stripped void.
    const md = [
      "import Foo from './foo';",
      "",
      "export const x = 1;",
      "",
      "Real prose that **must** still render.",
    ].join("\n");
    const html = render(md);
    expect(html).toMatch(/<strong[^>]*>must<\/strong>/);
    expect(html).toContain("Real prose that");
  });

  it("strips <script> tags and never executes inline JS", () => {
    const html = render(
      "<script>alert('xss')</script>\n\nSafe **body** continues.",
    );
    expect(html).not.toContain("<script");
    expect(html).not.toContain("alert(");
    expect(html).toMatch(/<strong[^>]*>body<\/strong>/);
  });

  it("strips on* event-handler attributes that try to ride on a raw <a> tag", () => {
    // The sanitiser's `<a>` allow-list only permits href + title, so
    // an event-handler attribute on a raw HTML link tag is dropped
    // (or the tag itself is dropped via `skipHtml`).
    const html = render(
      `<a href="https://example.com/" onmouseover="alert(1)">click</a>`,
    );
    expect(html).not.toMatch(/onmouseover\s*=/i);
    expect(html).not.toMatch(/<a[^>]*onmouseover/i);
  });

  it("refuses to render javascript: URLs", () => {
    const html = render(
      "[bad](javascript:alert(1)) and [good](https://example.com)",
    );
    // bad link drops its <a> wrapper but the visible text survives —
    // content is never silently lost.
    expect(html).not.toMatch(/href="javascript:/i);
    expect(html).toContain("bad");
    expect(html).toContain('href="https://example.com"');
  });

  it("strips <style> blocks before parsing", () => {
    const html = render(
      "<style>body { display: none }</style>\n\n**survives**",
    );
    expect(html).not.toContain("<style");
    expect(html).not.toContain("display: none");
    expect(html).toMatch(/<strong[^>]*>survives<\/strong>/);
  });

  it("does not skip content — empty bodies fall through cleanly", () => {
    const html = render("");
    // No error, no content, no parse-error block.
    expect(html).not.toContain('data-testid="article-parse-error"');
  });
});
