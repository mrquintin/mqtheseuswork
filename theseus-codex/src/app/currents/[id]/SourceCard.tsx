"use client";

import type { CSSProperties } from "react";
import { useRef, useState } from "react";
import Link from "next/link";

import type { PublicSource } from "@/lib/currentsTypes";
import { highlightSubstring } from "@/lib/highlight";
import CitationPopover from "@/components/CitationPopover";

interface SourceCardProps {
  source: PublicSource;
}

const cardStyle: CSSProperties = {
  background: "var(--currents-bg-elevated)",
  border: "1px solid var(--currents-border)",
  borderRadius: "6px",
  padding: "1rem",
};

const metaStyle: CSSProperties = {
  alignItems: "center",
  color: "var(--currents-muted)",
  display: "flex",
  flexWrap: "wrap",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.72rem",
  gap: "0.5rem",
  letterSpacing: "0.04em",
  marginBottom: "0.7rem",
  textTransform: "uppercase",
};

const kindStyle: CSSProperties = {
  border: "1px solid var(--currents-border)",
  borderRadius: "999px",
  color: "var(--currents-parchment-dim)",
  padding: "0.22rem 0.45rem",
};

const revokedBannerStyle: CSSProperties = {
  background: "rgba(201, 148, 74, 0.14)",
  border: "1px solid var(--currents-amber)",
  borderRadius: "6px",
  color: "var(--currents-amber)",
  fontSize: "0.86rem",
  marginBottom: "0.85rem",
  padding: "0.55rem 0.65rem",
};

const textStyle: CSSProperties = {
  color: "var(--currents-parchment)",
  fontSize: "0.98rem",
  lineHeight: 1.65,
  margin: 0,
  whiteSpace: "pre-wrap",
};

function normalizedKind(source: PublicSource): string {
  const kind = source.source_kind.trim().toLowerCase();
  if (kind === "conclusion" || kind === "claim") return kind;
  return kind || "rationale";
}

function fallbackCanonicalPath(source: PublicSource): string {
  const sourceId = encodeURIComponent(source.source_id);
  if (normalizedKind(source) === "claim") {
    return `/conclusions/${sourceId}#claim-${sourceId}`;
  }
  return `/c/${sourceId}`;
}

export function canonicalHref(source: PublicSource): string {
  return source.canonical_path || fallbackCanonicalPath(source);
}

export default function SourceCard({ source }: SourceCardProps) {
  const anchorRef = useRef<HTMLButtonElement | null>(null);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const kind = normalizedKind(source);
  const reason = source.revoked_reason?.trim() || "rationale revoked";
  const sourceText = source.source_text || "[internal rationale unavailable]";
  const popoverPublicUrl = source.canonical_path || null;
  const popoverCitation = {
    id: source.id,
    is_revoked: source.is_revoked,
    quoted_span: source.quoted_span,
    retrieval_score: source.retrieval_score,
    source_id: source.source_id,
    source_kind: source.source_kind,
    source_visibility: popoverPublicUrl ? "org" : null,
  };

  return (
    <article
      style={{
        ...cardStyle,
        borderColor: source.is_revoked
          ? "rgba(201, 148, 74, 0.72)"
          : cardStyle.borderColor,
      }}
    >
      <div style={metaStyle}>
        <span style={kindStyle}>{kind}</span>
      </div>

      {source.is_revoked ? (
        <div role="note" style={revokedBannerStyle}>
          Revoked: {reason}
        </div>
      ) : null}

      <p
        style={{
          ...textStyle,
          textDecoration: source.is_revoked ? "line-through" : undefined,
          textDecorationColor: source.is_revoked ? "var(--currents-amber)" : undefined,
        }}
      >
        {highlightSubstring(sourceText, source.quoted_span)}
      </p>

      <div
        style={{
          alignItems: "center",
          borderTop: "1px solid var(--currents-border)",
          display: "flex",
          flexWrap: "wrap",
          gap: "0.65rem",
          justifyContent: "space-between",
          marginTop: "0.9rem",
          paddingTop: "0.75rem",
        }}
      >
        <Link
          href={canonicalHref(source)}
          style={{
            color: "var(--currents-gold)",
            fontSize: "0.88rem",
            textDecoration: "none",
          }}
        >
          Go to canonical
        </Link>
        <button
          aria-expanded={popoverOpen}
          aria-haspopup="dialog"
          onClick={() => setPopoverOpen(true)}
          ref={anchorRef}
          style={{
            background: "transparent",
            border: "1px solid var(--currents-border)",
            borderRadius: "999px",
            color: "var(--currents-parchment-dim)",
            cursor: "pointer",
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "0.72rem",
            padding: "0.3rem 0.5rem",
          }}
          type="button"
        >
          Inspect source
        </button>
      </div>
      <CitationPopover
        anchorRef={anchorRef}
        citation={popoverCitation}
        conclusionText={sourceText}
        onClose={() => setPopoverOpen(false)}
        open={popoverOpen}
        publicUrl={popoverPublicUrl}
      />
    </article>
  );
}
