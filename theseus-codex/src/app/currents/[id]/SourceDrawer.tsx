import type { CSSProperties } from "react";
import Link from "next/link";

import type { PublicSource } from "@/lib/currentsTypes";
import { highlightSubstring } from "@/lib/highlight";

import { canonicalHref } from "./SourceCard";

interface SourceDrawerProps {
  selectedSource: PublicSource | null;
  sources: PublicSource[];
  onSelect: (sourceId: string) => void;
}

const drawerStyle: CSSProperties = {
  background: "var(--currents-bg-elevated)",
  border: "1px solid var(--currents-border)",
  borderRadius: "6px",
  padding: "0.9rem",
  position: "sticky",
  top: "1rem",
};

function kindLabel(source: PublicSource): string {
  const kind = source.source_kind.trim().toLowerCase();
  return kind === "conclusion" || kind === "claim" ? kind : kind || "source";
}

function percent(score: number): string {
  if (!Number.isFinite(score)) return "0%";
  const normalized = Math.abs(score) <= 1 ? score * 100 : score;
  return `${Math.round(normalized)}%`;
}

export default function SourceDrawer({
  selectedSource,
  sources,
  onSelect,
}: SourceDrawerProps) {
  return (
    <aside aria-label="Source drawer" style={drawerStyle}>
      <h2
        style={{
          color: "var(--currents-parchment)",
          fontFamily: "'Cinzel', serif",
          fontSize: "0.88rem",
          letterSpacing: "0.08em",
          margin: "0 0 0.65rem",
          textTransform: "uppercase",
        }}
      >
        Source drawer
      </h2>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.4rem",
          marginBottom: "0.8rem",
        }}
      >
        {sources.map((source, index) => (
          <button
            key={source.id}
            onClick={() => onSelect(source.source_id)}
            style={{
              background:
                selectedSource?.source_id === source.source_id
                  ? "rgba(212, 160, 23, 0.13)"
                  : "transparent",
              border:
                selectedSource?.source_id === source.source_id
                  ? "1px solid var(--currents-gold)"
                  : "1px solid var(--currents-border)",
              borderRadius: "999px",
              color: source.is_revoked
                ? "var(--currents-amber)"
                : "var(--currents-parchment-dim)",
              cursor: "pointer",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "0.7rem",
              padding: "0.28rem 0.45rem",
            }}
            type="button"
          >
            {index + 1}
          </button>
        ))}
      </div>

      {selectedSource ? (
        <div>
          <div
            style={{
              color: "var(--currents-muted)",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "0.72rem",
              letterSpacing: "0.04em",
              textTransform: "uppercase",
            }}
          >
            {kindLabel(selectedSource)} · score {percent(selectedSource.retrieval_score)}
          </div>

          {selectedSource.is_revoked ? (
            <div
              role="note"
              style={{
                background: "rgba(201, 148, 74, 0.14)",
                border: "1px solid var(--currents-amber)",
                borderRadius: "6px",
                color: "var(--currents-amber)",
                fontSize: "0.82rem",
                marginTop: "0.65rem",
                padding: "0.5rem",
              }}
            >
              Revoked: {selectedSource.revoked_reason?.trim() || "source revoked"}
            </div>
          ) : null}

          <p
            style={{
              color: "var(--currents-parchment-dim)",
              fontSize: "0.9rem",
              lineHeight: 1.55,
              margin: "0.75rem 0",
              maxHeight: "18rem",
              overflow: "auto",
              textDecoration: selectedSource.is_revoked ? "line-through" : undefined,
              textDecorationColor: selectedSource.is_revoked
                ? "var(--currents-amber)"
                : undefined,
              whiteSpace: "pre-wrap",
            }}
          >
            {highlightSubstring(
              selectedSource.source_text || "[source text unavailable]",
              selectedSource.quoted_span,
            )}
          </p>

          <Link
            href={canonicalHref(selectedSource)}
            style={{
              color: "var(--currents-gold)",
              fontSize: "0.86rem",
              textDecoration: "none",
            }}
          >
            Go to canonical
          </Link>
        </div>
      ) : (
        <p
          style={{
            color: "var(--currents-muted)",
            fontSize: "0.9rem",
            lineHeight: 1.5,
            margin: 0,
          }}
        >
          Select a source citation to inspect the quoted span, retrieval score,
          and canonical target.
        </p>
      )}
    </aside>
  );
}
