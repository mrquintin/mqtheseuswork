"use client";

import type { PublicCitation, PublicSource } from "@/lib/currentsTypes";
import { highlightFirst } from "@/lib/highlight";

// Permalink target for conclusion-kind sources. Claims don't have a public
// page, so they get no permalink regardless of what the server returns.
function resolvePermalink(source: PublicSource): string | null {
  if (source.permalink) return source.permalink;
  if (source.source_kind === "conclusion") {
    // Fallback slug built from the source_id — the c/[slug] route will
    // 404 gracefully if the conclusion isn't in the static bundle.
    return `/c/${encodeURIComponent(source.source_id)}`;
  }
  return null;
}

export function SourceCard({
  source,
  citation,
  active,
  scrollTargetRef,
}: {
  source: PublicSource;
  citation: PublicCitation;
  active: boolean;
  scrollTargetRef?: (el: HTMLDivElement | null) => void;
}) {
  const permalink = resolvePermalink(source);
  const borderColor = active
    ? "var(--currents-gold)"
    : "var(--currents-border)";
  const shadow = active
    ? "0 0 0 2px var(--currents-gold-glow)"
    : "none";

  return (
    <div
      ref={scrollTargetRef}
      id={`src-${source.source_id}`}
      data-testid="source-card"
      data-active={active ? "true" : "false"}
      style={{
        border: `1px solid ${borderColor}`,
        borderRadius: 4,
        padding: "0.7rem 0.8rem",
        marginBottom: "0.7rem",
        background: "var(--currents-surface)",
        boxShadow: shadow,
        transition: "border-color 400ms ease, box-shadow 400ms ease",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "0.5rem",
          marginBottom: "0.45rem",
          fontSize: "0.72rem",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--currents-parchment-dim)",
        }}
      >
        <span>
          {source.source_kind}
          {source.origin ? ` · ${source.origin}` : ""}
          {source.topic_hint ? ` · ${source.topic_hint}` : ""}
        </span>
        {permalink ? (
          <a
            href={permalink}
            data-testid="source-permalink"
            style={{
              color: "var(--currents-gold)",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              fontSize: "0.7rem",
            }}
          >
            permalink →
          </a>
        ) : null}
      </header>

      <div
        data-testid="source-body"
        style={{
          fontSize: "0.86rem",
          lineHeight: 1.5,
          color: "var(--currents-parchment)",
          whiteSpace: "pre-wrap",
          fontFamily: "'EB Garamond', Georgia, serif",
        }}
      >
        {highlightFirst(source.full_text, citation.quoted_span)}
      </div>

      <footer
        style={{
          marginTop: "0.55rem",
          display: "flex",
          justifyContent: "space-between",
          gap: "0.5rem",
          fontSize: "0.7rem",
          color: "var(--currents-muted)",
          letterSpacing: "0.04em",
        }}
      >
        <span title={source.source_id}>
          id · {source.source_id.slice(0, 12)}
        </span>
        <span>relevance · {citation.relevance_score.toFixed(2)}</span>
      </footer>
    </div>
  );
}
