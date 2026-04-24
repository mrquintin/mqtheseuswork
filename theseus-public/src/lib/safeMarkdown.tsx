import React from "react";

/**
 * Hand-rolled, strict markdown renderer for current-event opinion bodies.
 *
 * Contract:
 *   - Input is always short (<= 800 chars, enforced by the API contract).
 *   - Only supported tokens: paragraphs, **bold**, *italic*, `inline code`,
 *     [label](url) links.
 *   - No images, no headers, no code blocks, no raw HTML.
 *   - Output is a React tree. We NEVER call dangerouslySetInnerHTML, so
 *     every character left as text goes through React's auto-escaping —
 *     that alone handles the `<script>alert(1)</script>` case.
 *   - Links are forced http/https; anything else collapses to "#".
 */
export function renderSafeMarkdown(md: string): React.ReactNode {
  const paragraphs = (md || "").split(/\n\n+/);
  return paragraphs.map((p, i) => (
    <p key={i} style={{ margin: "0 0 0.5rem" }}>
      {renderInline(p)}
    </p>
  ));
}

function renderInline(text: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  // Order matters: bold (**..**) before italic (*..*) to avoid greedy
  // collisions on the single-asterisk branch.
  const re =
    /\*\*([^*\n]+)\*\*|\*([^*\n]+)\*|`([^`\n]+)`|\[([^\]\n]+)\]\(([^)\s]+)\)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1]) {
      out.push(<strong key={key++}>{m[1]}</strong>);
    } else if (m[2]) {
      out.push(<em key={key++}>{m[2]}</em>);
    } else if (m[3]) {
      out.push(<code key={key++}>{m[3]}</code>);
    } else if (m[4] && m[5]) {
      const url = m[5];
      const safe = /^https?:\/\//i.test(url) ? url : "#";
      out.push(
        <a
          key={key++}
          href={safe}
          target="_blank"
          rel="noopener nofollow ugc"
        >
          {m[4]}
        </a>,
      );
    }
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
