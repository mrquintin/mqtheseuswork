"use client";

import { useEffect, useState } from "react";
import type { PublicOpinion } from "@/lib/currentsTypes";
import {
  STANCE_COLOR,
  STANCE_LABEL,
  confidenceBand,
} from "@/lib/stanceStyles";
import { relativeTime } from "@/lib/relativeTime";
import { renderSafeMarkdown } from "@/lib/safeMarkdown";

const MAX_VISIBLE_CITATIONS = 3;

export function OpinionCard({ op }: { op: PublicOpinion }) {
  // Re-render every 60s so "Xm ago" stays fresh without forcing a reload.
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 60_000);
    return () => clearInterval(id);
  }, []);

  const stanceColor = STANCE_COLOR[op.stance];
  const stanceLabel = STANCE_LABEL[op.stance];
  const band = confidenceBand(op.confidence);
  const visible = op.citations.slice(0, MAX_VISIBLE_CITATIONS);
  const hidden = Math.max(0, op.citations.length - visible.length);

  return (
    <article
      className="currents-fade-in"
      data-testid="opinion-card"
      style={{
        background: "var(--currents-bg-elevated)",
        border: "1px solid var(--currents-border)",
        borderRadius: "10px",
        padding: "1.1rem 1.2rem",
        margin: "0 0 1rem",
        boxShadow: "0 1px 0 rgba(0,0,0,0.2)",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.55rem",
          flexWrap: "wrap",
          marginBottom: "0.6rem",
        }}
      >
        <span
          data-testid="stance-pill"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.35rem",
            padding: "0.18rem 0.55rem",
            borderRadius: "999px",
            border: `1px solid ${stanceColor}`,
            color: stanceColor,
            fontSize: "0.72rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            background: "rgba(0,0,0,0.25)",
          }}
        >
          {stanceLabel}
        </span>
        <span
          data-testid="confidence-band"
          title={`confidence ${op.confidence.toFixed(2)}`}
          style={{
            fontSize: "0.72rem",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--currents-parchment-dim)",
          }}
        >
          confidence · {band}
        </span>
        <span
          style={{
            fontSize: "0.72rem",
            color: "var(--currents-muted)",
            letterSpacing: "0.04em",
          }}
        >
          {relativeTime(op.generated_at)}
        </span>
        {op.topic_hint ? (
          <span
            style={{
              fontSize: "0.72rem",
              color: "var(--currents-parchment-dim)",
              fontStyle: "italic",
            }}
          >
            · {op.topic_hint}
          </span>
        ) : null}
      </header>

      <div
        style={{
          fontSize: "0.82rem",
          color: "var(--currents-parchment-dim)",
          marginBottom: "0.55rem",
        }}
      >
        <span>@{op.event_author_handle}</span>
        {" · "}
        <a
          href={op.event_source_url}
          target="_blank"
          rel="noopener nofollow ugc"
        >
          source
        </a>
      </div>

      <h2
        style={{
          margin: "0 0 0.6rem",
          fontFamily: "'EB Garamond', Georgia, serif",
          fontSize: "1.3rem",
          lineHeight: 1.25,
          color: "var(--currents-parchment)",
        }}
      >
        {op.headline}
      </h2>

      <div
        style={{
          fontSize: "0.98rem",
          lineHeight: 1.55,
          color: "var(--currents-parchment)",
        }}
      >
        {renderSafeMarkdown(op.body_markdown)}
      </div>

      {op.uncertainty_notes.length > 0 ? (
        <ul
          style={{
            margin: "0.35rem 0 0.5rem",
            paddingLeft: "1.1rem",
            fontSize: "0.82rem",
            color: "var(--currents-parchment-dim)",
            fontStyle: "italic",
          }}
        >
          {op.uncertainty_notes.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      ) : null}

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.4rem",
          flexWrap: "wrap",
          marginTop: "0.7rem",
        }}
      >
        {visible.map((c, i) => (
          <span
            key={`${c.source_kind}-${c.source_id}-${i}`}
            data-testid="citation-chip"
            style={{
              fontSize: "0.72rem",
              padding: "0.15rem 0.5rem",
              border: "1px solid var(--currents-border)",
              borderRadius: "999px",
              color: "var(--currents-parchment-dim)",
              background: "var(--currents-surface)",
              letterSpacing: "0.04em",
            }}
            title={c.quoted_span}
          >
            {c.source_kind} · {c.source_id.slice(0, 10)}
          </span>
        ))}
        {hidden > 0 ? (
          <span
            data-testid="more-chips"
            style={{
              fontSize: "0.72rem",
              color: "var(--currents-parchment-dim)",
            }}
          >
            +{hidden} more
          </span>
        ) : null}
      </div>

      <div
        style={{
          marginTop: "0.75rem",
          display: "flex",
          justifyContent: "flex-end",
        }}
      >
        <a
          href={`/currents/${encodeURIComponent(op.id)}#ask`}
          style={{
            fontSize: "0.82rem",
            letterSpacing: "0.04em",
          }}
        >
          Ask a follow-up →
        </a>
      </div>
    </article>
  );
}
