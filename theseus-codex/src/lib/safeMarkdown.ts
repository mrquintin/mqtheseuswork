import React from "react";

type InlineNode = React.ReactNode;

const LINK_REL = "noopener nofollow ugc";
const SCRIPT_TAG_RE = /<\s*\/?\s*script\b/i;

function safeExternalHref(rawUrl: string): string | null {
  const trimmed = rawUrl.trim();
  try {
    const url = new URL(trimmed);
    if (url.protocol === "http:" || url.protocol === "https:" || url.protocol === "mailto:") {
      return url.toString();
    }
  } catch {
    return null;
  }
  return null;
}

function pushText(nodes: InlineNode[], text: string) {
  if (!text) return;
  const previous = nodes.at(-1);
  if (typeof previous === "string") {
    nodes[nodes.length - 1] = previous + text;
    return;
  }
  nodes.push(text);
}

function parseInline(text: string, keyPrefix: string): InlineNode[] {
  const nodes: InlineNode[] = [];
  let index = 0;
  let key = 0;

  while (index < text.length) {
    if (text.startsWith("`", index)) {
      const end = text.indexOf("`", index + 1);
      if (end > index + 1) {
        nodes.push(
          React.createElement(
            "code",
            {
              key: `${keyPrefix}-code-${key++}`,
              style: {
                background: "rgba(232, 225, 211, 0.1)",
                border: "1px solid var(--currents-border)",
                borderRadius: "4px",
                color: "var(--currents-parchment)",
                fontSize: "0.88em",
                padding: "0.05rem 0.25rem",
              },
            },
            text.slice(index + 1, end),
          ),
        );
        index = end + 1;
        continue;
      }
    }

    if (text.startsWith("**", index)) {
      const end = text.indexOf("**", index + 2);
      if (end > index + 2) {
        nodes.push(
          React.createElement(
            "strong",
            { key: `${keyPrefix}-strong-${key++}` },
            parseInline(text.slice(index + 2, end), `${keyPrefix}-strong-${key}`),
          ),
        );
        index = end + 2;
        continue;
      }
    }

    if (text[index] === "*" && !text.startsWith("**", index)) {
      const end = text.indexOf("*", index + 1);
      if (end > index + 1 && !text.startsWith("*", end + 1)) {
        nodes.push(
          React.createElement(
            "em",
            { key: `${keyPrefix}-em-${key++}` },
            parseInline(text.slice(index + 1, end), `${keyPrefix}-em-${key}`),
          ),
        );
        index = end + 1;
        continue;
      }
    }

    if (text[index] === "[") {
      const labelEnd = text.indexOf("]", index + 1);
      if (labelEnd > index + 1 && text[labelEnd + 1] === "(") {
        const urlEnd = text.indexOf(")", labelEnd + 2);
        if (urlEnd > labelEnd + 2) {
          const label = text.slice(index + 1, labelEnd);
          const href = safeExternalHref(text.slice(labelEnd + 2, urlEnd));
          if (href) {
            nodes.push(
              React.createElement(
                "a",
                {
                  key: `${keyPrefix}-link-${key++}`,
                  href,
                  rel: LINK_REL,
                  target: "_blank",
                },
                parseInline(label, `${keyPrefix}-link-${key}`),
              ),
            );
          } else {
            pushText(nodes, label);
          }
          index = urlEnd + 1;
          continue;
        }
      }
    }

    pushText(nodes, text[index]);
    index += 1;
  }

  return nodes;
}

export function renderSafeMarkdown(md: string): React.ReactNode {
  const normalized = md.replace(/\r\n?/g, "\n").replace(/\0/g, "");
  const paragraphs = normalized
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.replace(/[ \t]*\n[ \t]*/g, " ").trim())
    .filter(Boolean);

  if (!paragraphs.length) return null;

  return paragraphs.map((paragraph, index) =>
    React.createElement(
      "p",
      {
        key: `paragraph-${index}`,
        style: index === 0 ? { marginTop: 0 } : undefined,
      },
      SCRIPT_TAG_RE.test(paragraph)
        ? paragraph
        : parseInline(paragraph, `paragraph-${index}`),
    ),
  );
}
