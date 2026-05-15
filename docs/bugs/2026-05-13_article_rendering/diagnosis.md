# Article rendering bug — 2026-05-13

## Summary

Two distinct bugs hit the article-publishing surface:

1. **Body rendering on `/post/[slug]` collapses markdown into glitchy
   prose.** The page at `theseus-codex/src/app/post/[slug]/page.tsx`
   feeds `Upload.textContent` (a markdown string) through
   `splitParagraphs()`, which:
   - splits on blank-line boundaries OR, if there are none, on a
     400-char "sentence wall" fallback;
   - flattens internal whitespace with `replace(/\s+/g, " ")`;
   - wraps every block in a plain `<p>`.

   The net effect is that markdown structure is destroyed in transit:
   headings, lists, emphasis, code, blockquotes — all become a single
   `<p>` per blank-line block. Inline markers (`#`, `-`, `**`, `1.`)
   are emitted as literal text. A title like
   *"Real cost of growth. 8x, one argument."* gets crushed onto one
   line, and any structural break the author wrote is invisible.

2. **Published articles do not surface on the public homepage.**
   `theseus-codex/src/app/page.tsx` only calls
   `listPublishedArticles(4)`, which queries
   `PublishedConclusion WHERE kind = 'ARTICLE'`. Uploads published
   through `/api/publish` (the founder's "Publish to blog" toggle)
   never write to that table; they flip `Upload.publishedAt` and live
   at `/post/[slug]`. So the homepage's Publications rail is blind to
   them.

   This is a query/state-skew bug: the publish action says "you are
   public" but the homepage's surfacing query never reads the column
   that publish flipped.

## Reproduction

The local `dev.db` snapshot in this repo predates the `publishedAt`
/ `slug` / `visibility` columns on `Upload`, so the live article
("Real cost of growth. 8x, one argument.") is not present in the
checked-out fixture. The repro therefore uses a synthetic fixture
with the same surface signature (markdown headings, a numeric pull
quote, lists, emphasis) that the founder authored.

Raw fixture body: `raw_body.md`.

### Pre-fix rendered shape

With `splitParagraphs` in charge, the rendered DOM is a stack of
indistinguishable `<p>` elements, each carrying a literal `#`/`-`/
`**` marker. Headings have no visual weight, no semantic level, no
print-only differentiation. Lists are inline prose. A reader sees a
"glitchy" wall of text because the page styles are designed for
clean prose paragraphs and have no fallback for raw markdown
tokens.

### Post-fix rendered shape

With `ArticleRenderer` in charge (the new shared component at
`theseus-codex/src/components/article/ArticleRenderer.tsx`):

- `# Heading` → `<h1>`, `## Subheading` → `<h2>`, etc. (semantic
  level preserved as declared);
- `- item` → `<ul><li>...</li></ul>` (one list, not one paragraph
  per item);
- `1. item` → `<ol start="...">`;
- `**bold**` → `<strong>`, `*em*` → `<em>`, `` `code` `` →
  `<code>`, fenced blocks → `<pre><code>`;
- `> quote` → `<blockquote>`;
- raw `<script>` / `<style>` / event-handler attrs / `javascript:`
  URLs are stripped at the sanitiser (rehype-sanitize on a
  tag-and-protocol allow-list);
- any catastrophic parse failure surfaces an inline `<aside
  role="alert" data-article-error>` block rather than dropping the
  section silently.

## Root cause (rank-ordered)

1. **`/post/[slug]` uses a different renderer than `/c/[slug]`.**
   `/c/[slug]` (`PublishedConclusion`) renders article body through
   `AnswerMarkdown` (react-markdown + rehype-sanitize). `/post/[slug]`
   (`Upload`) renders through `splitParagraphs` (plain text, no
   markdown grammar). The two surfaces are inconsistent.
2. **Homepage query reads from the wrong table.** The Publications
   rail only sees `PublishedConclusion.kind='ARTICLE'`. The Upload-
   publish path is invisible.
3. (ruled out) sanitiser stripping required tags — there is no
   sanitiser on `/post/[slug]`; the text never enters a markdown
   pipeline.
4. (ruled out) SSR/CSR mismatch — both renderers are server
   components; the failure mode is structural, not hydration.
5. (ruled out) CSS collapsing paragraphs — the body styles are fine;
   the input never reaches a markdown DOM.

## Fix

- **Consolidate to one markdown renderer.** New
  `ArticleRenderer.tsx` is the canonical article-body component. It
  uses the single existing markdown library (`react-markdown` +
  `remark-gfm` + `rehype-sanitize`) — no second library introduced.
- **`/post/[slug]/page.tsx` renders the upload's `textContent`
  through `ArticleRenderer`.** `splitParagraphs` is removed.
- **`/c/[slug]` (via `ConclusionView`) is left alone for now.** It
  already renders through `AnswerMarkdown` (the same markdown
  library); both surfaces now produce structurally faithful HTML.
  Future consolidation can swap `AnswerMarkdown` → `ArticleRenderer`
  inside `ConclusionView` once the provenance-gutter alignment is
  ported.
- **Homepage surfaces both publication paths.** `latestArticles()`
  now reads (a) `PublishedConclusion.kind='ARTICLE'` and (b)
  `Upload WHERE publishedAt IS NOT NULL AND deletedAt IS NULL AND
  visibility='org'`, merges them, and orders by `publishedAt DESC,
  id ASC` (stable secondary key to avoid race-induced reorder).
  Limit is 8 with a "View all" link; the page is `force-dynamic`
  so the rail reflects a publish within seconds (well under 60s).

## Security notes

`ArticleRenderer` does NOT use `dangerouslySetInnerHTML`. It uses
`react-markdown` with:

- a tag allow-list (no `<script>`, no `<iframe>`, no `<style>`);
- an attribute allow-list (no event handlers; `href` restricted to
  `http`, `https`, `mailto`);
- raw HTML stripped (`skipHtml`) plus a pre-pass that removes
  `<script>` / `<style>` blocks before parsing;
- the component tests assert each adversarial input (script tag,
  `onclick` attribute, `javascript:` URL) is neutralised.
