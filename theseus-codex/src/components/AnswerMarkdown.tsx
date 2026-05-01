"use client";

import type { CSSProperties, ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import {
  citationHref,
  ORACLE_CITATION_TOKEN,
  ORACLE_CITATION_TOKEN_EXACT,
  type ResolvedCitationMap,
} from "@/lib/oracleCitations";

interface AnswerMarkdownProps {
  children: string;
  citations?: ResolvedCitationMap;
  citationsResolver?: (token: string) => string | null;
}

interface MarkdownNode {
  type?: string;
  value?: string;
  children?: MarkdownNode[];
}

const allowedElements = [
  "p",
  "strong",
  "em",
  "ul",
  "ol",
  "li",
  "code",
  "pre",
  "blockquote",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
] as const;

const sanitizeSchema = {
  ...defaultSchema,
  tagNames: [...allowedElements],
  attributes: {
    code: ["className"],
    ol: ["start"],
  },
};

const containerStyle: CSSProperties = {
  fontFamily: "'EB Garamond', serif",
  fontSize: "1.08rem",
  lineHeight: 1.65,
  color: "var(--parchment)",
  marginTop: "0.7rem",
};

const paragraphStyle: CSSProperties = {
  margin: "0 0 0.85rem",
};

const strongStyle: CSSProperties = {
  color: "var(--amber)",
  fontWeight: 700,
};

const listStyle: CSSProperties = {
  margin: "0.45rem 0 0.9rem",
  paddingLeft: "1.35rem",
};

const listItemStyle: CSSProperties = {
  margin: "0.18rem 0",
  paddingLeft: "0.15rem",
};

const citationCodeStyle: CSSProperties = {
  fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)",
  fontSize: "0.72em",
  color: "var(--amber)",
  background: "rgba(214, 156, 63, 0.12)",
  border: "1px solid rgba(214, 156, 63, 0.22)",
  borderRadius: "4px",
  padding: "0.08rem 0.28rem",
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

const codeStyle: CSSProperties = {
  fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)",
  fontSize: "0.84em",
  color: "var(--parchment)",
  background: "rgba(255, 245, 220, 0.08)",
  border: "1px solid rgba(255, 245, 220, 0.12)",
  borderRadius: "4px",
  padding: "0.08rem 0.28rem",
};

const preStyle: CSSProperties = {
  margin: "0.7rem 0 0.95rem",
  padding: "0.85rem 1rem",
  overflowX: "auto",
  background: "rgba(0, 0, 0, 0.22)",
  border: "1px solid var(--amber-deep)",
};

const blockquoteStyle: CSSProperties = {
  margin: "0.75rem 0 1rem",
  paddingLeft: "1rem",
  borderLeft: "2px solid var(--amber-deep)",
  color: "var(--parchment-dim)",
};

const headingStyle: CSSProperties = {
  fontFamily: "'Cinzel', serif",
  fontSize: "1rem",
  lineHeight: 1.35,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  color: "var(--amber)",
  margin: "0.85rem 0 0.45rem",
  fontWeight: 600,
};

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

      const nextChildren: MarkdownNode[] = [];
      for (const child of parent.children) {
        if (child.type === "text" && typeof child.value === "string") {
          nextChildren.push(...splitCitationTokens(child.value));
          continue;
        }

        if (child.type !== "inlineCode" && child.type !== "code") {
          visit(child);
        }
        nextChildren.push(child);
      }

      parent.children = nextChildren;
    }

    visit(tree);
  };
}

function stripUnsafeHtmlBlocks(markdown: string): string {
  return markdown
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, "");
}

function textFromReactNode(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textFromReactNode).join("");
  return "";
}

export function AnswerMarkdown({
  children,
  citations = {},
  citationsResolver = () => null,
}: AnswerMarkdownProps) {
  const components: Components = {
    p({ node: _node, style: _style, ...props }) {
      return <p style={paragraphStyle} {...props} />;
    },
    strong({ node: _node, style: _style, ...props }) {
      return <strong style={strongStyle} {...props} />;
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

      return href ? (
        <a
          href={href}
          rel="noopener"
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
    pre({ node: _node, style: _style, ...props }) {
      return <pre style={preStyle} {...props} />;
    },
    blockquote({ node: _node, style: _style, ...props }) {
      return <blockquote style={blockquoteStyle} {...props} />;
    },
    h1({ node: _node, style: _style, ...props }) {
      return <h3 style={headingStyle} {...props} />;
    },
    h2({ node: _node, style: _style, ...props }) {
      return <h3 style={headingStyle} {...props} />;
    },
    h3({ node: _node, style: _style, ...props }) {
      return <h3 style={headingStyle} {...props} />;
    },
    h4({ node: _node, style: _style, ...props }) {
      return <h3 style={headingStyle} {...props} />;
    },
    h5({ node: _node, style: _style, ...props }) {
      return <h3 style={headingStyle} {...props} />;
    },
    h6({ node: _node, style: _style, ...props }) {
      return <h3 style={headingStyle} {...props} />;
    },
  };

  return (
    <div style={containerStyle}>
      <Markdown
        allowedElements={[...allowedElements]}
        components={components}
        rehypePlugins={[[rehypeSanitize, sanitizeSchema]]}
        remarkPlugins={[remarkGfm, remarkCitationTokens]}
        skipHtml
        unwrapDisallowed
      >
        {stripUnsafeHtmlBlocks(children)}
      </Markdown>
    </div>
  );
}

export default AnswerMarkdown;
