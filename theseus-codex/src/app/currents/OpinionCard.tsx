import type { CSSProperties } from "react";
import Link from "next/link";

import type { PublicCitation, PublicOpinion } from "@/lib/currentsTypes";
import { relativeTime } from "@/lib/relativeTime";
import { renderSafeMarkdown } from "@/lib/safeMarkdown";

type StanceKey = "agrees" | "disagrees" | "complicates" | "abstained";
type ConfidenceBand = "low" | "mid" | "high";

const supportedStances = new Set<StanceKey>([
  "agrees",
  "disagrees",
  "complicates",
  "abstained",
]);

function stanceKey(rawStance: string): StanceKey {
  const normalized = rawStance.trim().toLowerCase();
  if (supportedStances.has(normalized as StanceKey)) return normalized as StanceKey;
  if (["agree", "support", "supports"].includes(normalized)) return "agrees";
  if (["disagree", "oppose", "opposes", "rejects", "refutes"].includes(normalized)) {
    return "disagrees";
  }
  if (["complicate", "mixed", "qualifies", "qualified"].includes(normalized)) {
    return "complicates";
  }
  if (["abstain", "abstains"].includes(normalized)) return "abstained";
  return "abstained";
}

function confidenceBand(confidence: number): ConfidenceBand {
  if (!Number.isFinite(confidence)) return "low";
  if (confidence < 0.4) return "low";
  if (confidence < 0.75) return "mid";
  return "high";
}

function sourceLabel(citation: PublicCitation): string {
  const normalized = citation.source_kind.trim().toLowerCase();
  if (normalized === "conclusion") return "conclusion";
  if (normalized === "claim") return "claim";
  return normalized || "source";
}

function authorHandle(opinion: PublicOpinion): string | null {
  const handle = opinion.event?.author_handle?.trim();
  if (!handle) return null;
  return handle.startsWith("@") ? handle : `@${handle}`;
}

const cardStyle: CSSProperties = {
  background: "var(--currents-bg-elevated)",
  border: "1px solid var(--currents-border)",
  borderRadius: "6px",
  boxShadow: "0 12px 32px rgba(0, 0, 0, 0.18)",
  padding: "1rem 1rem 0.9rem",
};

const metaRowStyle: CSSProperties = {
  alignItems: "center",
  color: "var(--currents-muted)",
  display: "flex",
  flexWrap: "wrap",
  fontSize: "0.74rem",
  gap: "0.45rem",
  letterSpacing: "0.03em",
  marginBottom: "0.65rem",
};

const pillBaseStyle: CSSProperties = {
  borderRadius: "999px",
  fontSize: "0.68rem",
  fontWeight: 700,
  letterSpacing: "0.08em",
  lineHeight: 1,
  padding: "0.32rem 0.48rem",
  textTransform: "uppercase",
};

const headlineStyle: CSSProperties = {
  fontFamily: "'EB Garamond', serif",
  fontSize: "1.15rem",
  lineHeight: 1.25,
  margin: "0 0 0.55rem",
};

const bodyStyle: CSSProperties = {
  color: "var(--currents-parchment)",
  fontSize: "0.95rem",
  lineHeight: 1.6,
};

const sourceStripStyle: CSSProperties = {
  alignItems: "center",
  borderTop: "1px solid var(--currents-border)",
  display: "flex",
  flexWrap: "wrap",
  gap: "0.45rem",
  marginTop: "0.9rem",
  paddingTop: "0.75rem",
};

const mutedStyle: CSSProperties = {
  color: "var(--currents-muted)",
  fontSize: "0.78rem",
};

interface OpinionCardProps {
  opinion: PublicOpinion;
  className?: string;
}

export default function OpinionCard({ opinion, className }: OpinionCardProps) {
  const stance = stanceKey(opinion.stance);
  const stanceColor = `var(--currents-stance-${stance})`;
  const confidence = confidenceBand(opinion.confidence);
  const href = `/currents/${encodeURIComponent(opinion.id)}`;
  const topic = opinion.topic_hint || opinion.event?.topic_hint || "untagged";
  const shownCitations = opinion.citations.slice(0, 3);
  const hiddenCitationCount = Math.max(0, opinion.citations.length - shownCitations.length);
  const handle = authorHandle(opinion);
  const sourceName = opinion.event?.source || "external source";

  return (
    <article
      className={className}
      style={{
        ...cardStyle,
        borderLeft: `4px solid ${stanceColor}`,
      }}
    >
      <div style={metaRowStyle}>
        <span
          style={{
            ...pillBaseStyle,
            border: `1px solid ${stanceColor}`,
            color: stanceColor,
          }}
        >
          {stance}
        </span>
        <span
          title={`confidence ${Math.round(opinion.confidence * 100)}%`}
          style={{
            ...pillBaseStyle,
            background: "rgba(232, 225, 211, 0.08)",
            color: "var(--currents-parchment-dim)",
          }}
        >
          {confidence}
        </span>
        <span>{topic}</span>
        <span>· {relativeTime(opinion.generated_at)}</span>
      </div>

      <h2 style={headlineStyle}>
        <Link
          href={href}
          style={{
            color: "var(--currents-parchment)",
            textDecoration: "none",
          }}
        >
          {opinion.headline}
        </Link>
      </h2>

      <div style={bodyStyle}>{renderSafeMarkdown(opinion.body_markdown)}</div>

      {opinion.uncertainty_notes.length ? (
        <div
          style={{
            color: "var(--currents-amber)",
            fontSize: "0.88rem",
            fontStyle: "italic",
            lineHeight: 1.5,
            marginTop: "0.7rem",
          }}
        >
          {opinion.uncertainty_notes.map((note) => (
            <p key={note} style={{ margin: "0.2rem 0" }}>
              {note}
            </p>
          ))}
        </div>
      ) : null}

      {shownCitations.length ? (
        <div aria-label="Source citations" style={sourceStripStyle}>
          {shownCitations.map((citation) => (
            <Link
              key={citation.id}
              href={`${href}#src-${encodeURIComponent(citation.source_id)}`}
              style={{
                border: "1px solid var(--currents-border)",
                borderRadius: "999px",
                color: "var(--currents-parchment-dim)",
                fontSize: "0.78rem",
                padding: "0.28rem 0.5rem",
                textDecoration: "none",
              }}
            >
              ⸺ {sourceLabel(citation)}
            </Link>
          ))}
          {hiddenCitationCount ? (
            <span style={{ ...mutedStyle, padding: "0.28rem 0" }}>
              +{hiddenCitationCount} more
            </span>
          ) : null}
        </div>
      ) : null}

      <div
        style={{
          alignItems: "center",
          display: "flex",
          flexWrap: "wrap",
          gap: "0.65rem",
          justifyContent: "space-between",
          marginTop: "0.8rem",
        }}
      >
        <Link
          href={`${href}#ask`}
          style={{
            color: "var(--currents-gold)",
            fontSize: "0.86rem",
            textDecoration: "none",
          }}
        >
          Ask a follow-up →
        </Link>
        <span style={mutedStyle}>
          {handle ? `${handle} · ` : ""}
          {opinion.event?.url ? (
            <a
              href={opinion.event.url}
              rel="noopener nofollow ugc"
              target="_blank"
              style={{ color: "var(--currents-muted)" }}
            >
              {sourceName}
            </a>
          ) : (
            sourceName
          )}
        </span>
      </div>
    </article>
  );
}
