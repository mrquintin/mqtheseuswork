import type { CSSProperties } from "react";

import type { PublicOpinion, PublicSource } from "@/lib/currentsTypes";

interface AuditTrailProps {
  opinion: PublicOpinion;
  sources: PublicSource[];
  onSourceSelect?: (sourceId: string) => void;
}

const panelStyle: CSSProperties = {
  background: "rgba(232, 225, 211, 0.03)",
  border: "1px solid var(--currents-border)",
  borderRadius: "6px",
  padding: "0.9rem",
};

const rowStyle: CSSProperties = {
  color: "var(--currents-parchment-dim)",
  fontSize: "0.9rem",
  lineHeight: 1.45,
  margin: "0.35rem 0",
};

const scoreRowStyle: CSSProperties = {
  alignItems: "center",
  color: "var(--currents-muted)",
  display: "flex",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.72rem",
  gap: "0.45rem",
  justifyContent: "space-between",
  lineHeight: 1.35,
  marginTop: "0.45rem",
};

function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return count === 1 ? singular : pluralForm;
}

function generatedAgo(iso: string, now = Date.now()): string {
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return "unknown time ago";

  const seconds = Math.max(0, Math.floor((now - then) / 1000));
  if (seconds < 60) return `${seconds} ${plural(seconds, "second")} ago`;

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} ${plural(minutes, "minute")} ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ${plural(hours, "hour")} ago`;

  const days = Math.floor(hours / 24);
  return `${days} ${plural(days, "day")} ago`;
}

function percent(value: number): string {
  if (!Number.isFinite(value)) return "0%";
  const normalized = Math.abs(value) <= 1 ? value * 100 : value;
  return `${Math.round(normalized)}%`;
}

function sourceLabel(source: PublicSource, index: number): string {
  const kind = source.source_kind.trim().toLowerCase() || "source";
  return `${index + 1}. ${kind}`;
}

export default function AuditTrail({ opinion, sources, onSourceSelect }: AuditTrailProps) {
  const revokedCount = sources.filter((source) => source.is_revoked).length;

  return (
    <aside aria-label="Audit trail" style={panelStyle}>
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
        Audit trail
      </h2>
      <p style={rowStyle}>generated {generatedAgo(opinion.generated_at)}</p>
      <p style={rowStyle}>model {opinion.model_name}</p>
      <p style={rowStyle}>confidence {percent(opinion.confidence)}</p>
      {revokedCount > 0 ? (
        <p style={{ ...rowStyle, color: "var(--currents-amber)" }}>
          {revokedCount} {plural(revokedCount, "source")} revoked
        </p>
      ) : null}
      <a
        href="#ask"
        id="ask"
        style={{
          color: "var(--currents-gold)",
          display: "inline-block",
          fontSize: "0.9rem",
          marginTop: "0.35rem",
          textDecoration: "none",
        }}
      >
        Ask a follow-up
      </a>

      {sources.length ? (
        <div
          aria-label="Retrieval scores"
          style={{
            borderTop: "1px solid var(--currents-border)",
            marginTop: "0.9rem",
            paddingTop: "0.75rem",
          }}
        >
          {sources.map((source, index) => (
            <div key={source.id} style={scoreRowStyle}>
              <a
                href={`#src-${encodeURIComponent(source.source_id)}`}
                onClick={(event) => {
                  if (!onSourceSelect) return;
                  event.preventDefault();
                  onSourceSelect(source.source_id);
                }}
                style={{
                  color: source.is_revoked
                    ? "var(--currents-amber)"
                    : "var(--currents-muted)",
                  textDecoration: "none",
                }}
              >
                {sourceLabel(source, index)}
              </a>
              <span>
                {percent(source.retrieval_score)}
                {source.is_revoked ? " revoked" : ""}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </aside>
  );
}
