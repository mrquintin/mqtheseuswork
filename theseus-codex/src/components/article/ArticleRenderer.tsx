"use client";

import { type CSSProperties, type ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import {
  citationHref,
  ORACLE_CITATION_TOKEN,
  ORACLE_CITATION_TOKEN_EXACT,
  type ResolvedCitationMap,
} from "@/lib/oracleCitations";

/**
 * Canonical article-body renderer for the public surface.
 *
 * One renderer for both Upload-published blog posts (`/post/[slug]`)
 * and PublishedConclusion articles (`/c/[slug]`), so draft preview
 * and published view produce identical HTML.
 *
 * Pipeline: react-markdown → remark-gfm → rehype-sanitize. Raw HTML
 * is dropped (`skipHtml`), and `<script>` / `<style>` blocks are
 * pre-stripped before parsing so they cannot reach the tree even by
 * accident. The sanitizer's tag and protocol allow-lists are the
 * primary defense — the pre-strip is belt-and-suspenders.
 *
 * Heading levels are preserved as declared in the source: an h2 in
 * the markdown is an h2 in the DOM. The page chrome owns the h1
 * (post title); body headings stack underneath.
 *
 * If the markdown parser throws (it rarely does — react-markdown is
 * forgiving and emits literal text for malformed input), we render
 * an inline `<aside role="alert">` block with the failure message
 * and the unparsed body in a `<pre>`. Nothing is silently dropped.
 */

export interface ArticleRendererProps {
  body: string;
  citations?: ResolvedCitationMap;
  citationsResolver?: (token: string) => string | null;
  className?: string;
  testId?: string;
}

interface MarkdownNode {
  type?: string;
  value?: string;
  children?: MarkdownNode[];
}

const ALLOWED_ELEMENTS = [
  "p",
  "strong",
  "em",
  "del",
  "ul",
  "ol",
  "li",
  "code",
  "pre",
  "blockquote",
  "hr",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "a",
  "table",
  "thead",
  "tbody",
  "tr",
  "th",
  "td",
] as const;

const SAFE_HREF_PROTOCOLS = ["http", "https", "mailto"];

const SANITIZE_SCHEMA = {
  ...defaultSchema,
  tagNames: [...ALLOWED_ELEMENTS],
  attributes: {
    code: ["className"],
    ol: ["start"],
    a: ["href", "title"],
    th: ["align"],
    td: ["align"],
  },
  protocols: {
    ...(defaultSchema.protocols ?? {}),
    href: SAFE_HREF_PROTOCOLS,
  },
};

const containerStyle: CSSProperties = {
  fontFamily: "'EB Garamond', 'Iowan Old Style', Georgia, serif",
  fontSize: "1.1rem",
  lineHeight: 1.7,
  color: "var(--parchment)",
};

const paragraphStyle: CSSProperties = {
  margin: "0 0 1.1rem",
};

const strongStyle: CSSProperties = {
  color: "var(--amber)",
  fontWeight: 700,
};

const emStyle: CSSProperties = {
  fontStyle: "italic",
};

const listStyle: CSSProperties = {
  margin: "0.55rem 0 1.1rem",
  paddingLeft: "1.45rem",
};

const listItemStyle: CSSProperties = {
  margin: "0.22rem 0",
  paddingLeft: "0.15rem",
};

const codeStyle: CSSProperties = {
  fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)",
  fontSize: "0.86em",
  color: "var(--parchment)",
  background: "rgba(255, 245, 220, 0.08)",
  border: "1px solid rgba(255, 245, 220, 0.12)",
  borderRadius: "4px",
  padding: "0.08rem 0.28rem",
};

const preStyle: CSSProperties = {
  margin: "0.85rem 0 1.15rem",
  padding: "0.85rem 1rem",
  overflowX: "auto",
  background: "rgba(0, 0, 0, 0.22)",
  border: "1px solid var(--amber-deep)",
  fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)",
  fontSize: "0.86rem",
  lineHeight: 1.55,
};

const blockquoteStyle: CSSProperties = {
  margin: "0.85rem 0 1.15rem",
  paddingLeft: "1rem",
  borderLeft: "2px solid var(--amber-deep)",
  color: "var(--parchment-dim)",
  fontStyle: "italic",
};

const hrStyle: CSSProperties = {
  border: 0,
  borderTop: "1px solid var(--stroke)",
  margin: "1.6rem 0",
};

const headingBase: CSSProperties = {
  fontFamily: "'EB Garamond', 'Iowan Old Style', Georgia, serif",
  letterSpacing: "-0.005em",
  color: "var(--amber)",
  fontWeight: 600,
};

const headingStyles: Record<"h1" | "h2" | "h3" | "h4" | "h5" | "h6", CSSProperties> = {
  h1: { ...headingBase, fontSize: "1.85rem", lineHeight: 1.22, margin: "1.6rem 0 0.7rem" },
  h2: { ...headingBase, fontSize: "1.5rem", lineHeight: 1.25, margin: "1.4rem 0 0.6rem" },
  h3: { ...headingBase, fontSize: "1.25rem", lineHeight: 1.3, margin: "1.2rem 0 0.5rem" },
  h4: { ...headingBase, fontSize: "1.1rem", lineHeight: 1.32, margin: "1.0rem 0 0.45rem" },
  h5: { ...headingBase, fontSize: "1.0rem", lineHeight: 1.35, margin: "0.9rem 0 0.4rem" },
  h6: { ...headingBase, fontSize: "0.95rem", lineHeight: 1.4, margin: "0.85rem 0 0.4rem" },
};

const linkStyle: CSSProperties = {
  color: "var(--amber)",
  textDecoration: "underline",
  textUnderlineOffset: "2px",
};

const citationCodeStyle: CSSProperties = {
  fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)",
  fontSize: "0.74em",
  color: "var(--amber)",
  background: "rgba(214, 156, 63, 0.12)",
  border: "1px solid rgba(214, 156, 63, 0.22)",
  borderRadius: "4px",
  padding: "0.08rem 0.3rem",
  whiteSpace: "nowrap",
};

const unresolvedCitationStyle: CSSProperties = {
  ...citationCodeStyle,
  color: "var(--ember)",
  background: "rgba(201, 74, 31, 0.12)",
  border: "1px solid rgba(201, 74, 31, 0.34)",
};

const citationLinkStyle: CSSProperties = {
  color: "inherit",
  textDecoration: "none",
};

const errorBlockStyle: CSSProperties = {
  background: "rgba(201, 74, 31, 0.1)",
  border: "1px solid rgba(201, 74, 31, 0.4)",
  borderRadius: "4px",
  color: "var(--parchment)",
  margin: "1rem 0",
  padding: "0.85rem 1rem",
};

const errorTitleStyle: CSSProperties = {
  color: "var(--ember)",
  fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)",
  fontSize: "0.7rem",
  letterSpacing: "0.2em",
  margin: "0 0 0.4rem",
  textTransform: "uppercase",
};

const errorBodyStyle: CSSProperties = {
  margin: "0 0 0.4rem",
  fontSize: "0.95rem",
  lineHeight: 1.5,
};

function stripUnsafeBlocks(markdown: string): string {
  // Defense in depth on top of the sanitizer's tag allow-list.
  return markdown
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, "");
}

function splitCitationTokens(value: string): MarkdownNode[] {
  const nodes: MarkdownNode[] = [];
  let cursor = 0;
  ORACLE_CITATION_TOKEN.lastIndex = 0;

  for (const match of value.matchAll(ORACLE_CITATION_TOKEN)) {
    if (match.index === undefined) continue;
    if (match.index > cursor) {
      nodes.push({ type: "text", value: value.slice(cursor, match.index) });
    }
    nodes.push({ type: "inlineCode", value: match[0] });
    cursor = match.index + match[0].length;
  }

  if (cursor < value.length) {
    nodes.push({ type: "text", value: value.slice(cursor) });
  }

  return nodes.length > 0 ? nodes : [{ type: "text", value }];
}

function remarkCitationTokens() {
  return (tree: MarkdownNode) => {
    function visit(parent: MarkdownNode) {
      if (!parent.children) return;
      const next: MarkdownNode[] = [];
      for (const child of parent.children) {
        if (child.type === "text" && typeof child.value === "string") {
          next.push(...splitCitationTokens(child.value));
          continue;
        }
        if (child.type !== "inlineCode" && child.type !== "code") {
          visit(child);
        }
        next.push(child);
      }
      parent.children = next;
    }
    visit(tree);
  };
}

function textFromReactNode(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textFromReactNode).join("");
  return "";
}

function isSafeLinkHref(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const trimmed = value.trim();
  if (!trimmed) return false;
  if (trimmed.startsWith("/") || trimmed.startsWith("#")) return true;
  const lower = trimmed.toLowerCase();
  return SAFE_HREF_PROTOCOLS.some((p) => lower.startsWith(`${p}:`));
}

function InlineParseError({
  message,
  source,
}: {
  message: string;
  source: string;
}) {
  return (
    <aside
      data-article-error
      data-testid="article-parse-error"
      role="alert"
      style={errorBlockStyle}
    >
      <p className="mono" style={errorTitleStyle}>
        Renderer failed to parse this section
      </p>
      <p style={errorBodyStyle}>{message}</p>
      <pre style={{ ...preStyle, margin: 0 }}>{source}</pre>
    </aside>
  );
}

export function ArticleRenderer({
  body,
  citations = {},
  citationsResolver = () => null,
  className,
  testId,
}: ArticleRendererProps) {
  const components: Components = {
    p({ node: _node, style: _style, ...props }) {
      return <p style={paragraphStyle} {...props} />;
    },
    strong({ node: _node, style: _style, ...props }) {
      return <strong style={strongStyle} {...props} />;
    },
    em({ node: _node, style: _style, ...props }) {
      return <em style={emStyle} {...props} />;
    },
    ul({ node: _node, style: _style, ...props }) {
      return <ul style={listStyle} {...props} />;
    },
    ol({ node: _node, style: _style, ...props }) {
      return <ol style={listStyle} {...props} />;
    },
    li({ node: _node, style: _style, ...props }) {
      return <li style={listItemStyle} {...props} />;
    },
    hr() {
      return <hr style={hrStyle} />;
    },
    blockquote({ node: _node, style: _style, ...props }) {
      return <blockquote style={blockquoteStyle} {...props} />;
    },
    pre({ node: _node, style: _style, ...props }) {
      return <pre style={preStyle} {...props} />;
    },
    a({ node: _node, style: _style, href, ...props }) {
      if (!isSafeLinkHref(href)) {
        // Drop the link wrapper but keep the visible text so content
        // is never silently lost.
        return <span {...props} />;
      }
      const external = /^https?:/i.test(href);
      return (
        <a
          href={href}
          rel={external ? "noopener noreferrer" : undefined}
          style={linkStyle}
          target={external ? "_blank" : undefined}
          {...props}
        />
      );
    },
    code({ node: _node, style: _style, children: codeChildren, ...props }) {
      const token = textFromReactNode(codeChildren).trim();
      const isCitation = ORACLE_CITATION_TOKEN_EXACT.test(token);
      const citation = isCitation ? citations[token] : undefined;
      const href = citation
        ? citationHref(citation)
        : isCitation
          ? citationsResolver(token)
          : null;

      if (isCitation && citation && !href) {
        return (
          <span
            className="mono"
            style={unresolvedCitationStyle}
            title="Source not found in corpus — possible model hallucination"
          >
            {codeChildren}
          </span>
        );
      }

      const code = (
        <code
          className="mono"
          style={isCitation ? citationCodeStyle : codeStyle}
          {...props}
        >
          {codeChildren}
        </code>
      );

      return href && isSafeLinkHref(href) ? (
        <a
          href={href}
          rel="noopener noreferrer"
          style={citationLinkStyle}
          target="_blank"
          title={citation?.preview || undefined}
        >
          {code}
        </a>
      ) : (
        code
      );
    },
    h1({ node: _node, style: _style, ...props }) {
      return <h1 style={headingStyles.h1} {...props} />;
    },
    h2({ node: _node, style: _style, ...props }) {
      return <h2 style={headingStyles.h2} {...props} />;
    },
    h3({ node: _node, style: _style, ...props }) {
      return <h3 style={headingStyles.h3} {...props} />;
    },
    h4({ node: _node, style: _style, ...props }) {
      return <h4 style={headingStyles.h4} {...props} />;
    },
    h5({ node: _node, style: _style, ...props }) {
      return <h5 style={headingStyles.h5} {...props} />;
    },
    h6({ node: _node, style: _style, ...props }) {
      return <h6 style={headingStyles.h6} {...props} />;
    },
  };

  const source = stripUnsafeBlocks(body);

  let rendered: ReactNode;
  try {
    rendered = (
      <Markdown
        allowedElements={[...ALLOWED_ELEMENTS]}
        components={components}
        rehypePlugins={[[rehypeSanitize, SANITIZE_SCHEMA]]}
        remarkPlugins={[remarkGfm, remarkCitationTokens]}
        skipHtml
        unwrapDisallowed
      >
        {source}
      </Markdown>
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown parse error";
    rendered = <InlineParseError message={message} source={body} />;
  }

  return (
    <div
      className={className ?? "public-article-body"}
      data-testid={testId}
      style={containerStyle}
    >
      {rendered}
    </div>
  );
}

export default ArticleRenderer;
