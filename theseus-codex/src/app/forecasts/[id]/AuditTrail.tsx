import type { CSSProperties } from "react";

import type {
  PublicForecastCitation,
  PublicForecastSource,
} from "@/lib/forecastsTypes";

interface AuditTrailProps {
  citations: PublicForecastCitation[];
  sources: PublicForecastSource[];
}

const shellStyle: CSSProperties = {
  background: "rgba(232, 225, 211, 0.035)",
  border: "1px solid var(--forecasts-border)",
  borderRadius: "6px",
  color: "var(--forecasts-parchment)",
  padding: "0.95rem",
};

const summaryStyle: CSSProperties = {
  color: "var(--forecasts-cool-gold)",
  cursor: "pointer",
  fontFamily: "'Cinzel', serif",
  fontSize: "0.92rem",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const tableStyle: CSSProperties = {
  borderCollapse: "collapse",
  fontSize: "0.86rem",
  marginTop: "0.85rem",
  width: "100%",
};

const cellStyle: CSSProperties = {
  borderTop: "1px solid var(--forecasts-border)",
  padding: "0.55rem 0.45rem",
  textAlign: "left",
  verticalAlign: "top",
};

function sourceKey(sourceType: string, sourceId: string): string {
  return `${sourceType.trim().toUpperCase()}/${sourceId}`;
}

function scoreLabel(score: number | null): string {
  if (score === null || !Number.isFinite(score)) return "n/a";
  return score.toFixed(2);
}

function preview(text: string): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > 240 ? `${normalized.slice(0, 240)}...` : normalized;
}

export default function AuditTrail({ citations, sources }: AuditTrailProps) {
  const citedKeys = new Set(
    citations.map((citation) => sourceKey(citation.source_type, citation.source_id)),
  );

  return (
    <details aria-label="Retrieval audit trail" open style={shellStyle}>
      <summary style={summaryStyle}>Retrieval audit</summary>
      <p
        style={{
          color: "var(--forecasts-parchment-dim)",
          fontSize: "0.86rem",
          lineHeight: 1.45,
          margin: "0.65rem 0 0",
        }}
      >
        Every retrieved source supplied to this component is shown here; rows
        that appear in the final reasoning are marked cited.
      </p>

      <table style={tableStyle}>
        <thead>
          <tr style={{ color: "var(--forecasts-muted)" }}>
            <th style={cellStyle}>Source</th>
            <th style={cellStyle}>Relevance</th>
            <th style={cellStyle}>Status</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => {
            const key = sourceKey(source.source_type, source.source_id);
            const cited = citedKeys.has(key);
            return (
              <tr key={`${source.id}-${key}`} title={preview(source.source_text)}>
                <td className="mono" style={cellStyle}>
                  {key}
                </td>
                <td className="mono" style={cellStyle}>
                  {scoreLabel(source.retrieval_score)}
                </td>
                <td
                  style={{
                    ...cellStyle,
                    color: cited
                      ? "var(--forecasts-prob-yes)"
                      : "var(--forecasts-muted)",
                    fontWeight: cited ? 700 : 400,
                    textTransform: cited ? "uppercase" : undefined,
                  }}
                >
                  {cited ? "CITED" : "dropped"}
                </td>
              </tr>
            );
          })}
          {!sources.length ? (
            <tr>
              <td
                colSpan={3}
                style={{
                  ...cellStyle,
                  color: "var(--forecasts-muted)",
                  fontStyle: "italic",
                }}
              >
                No retrieved sources were returned by the public source endpoint.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </details>
  );
}
