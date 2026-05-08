"use client";

import { useState } from "react";

import type { PublicReconciliation } from "@/lib/currentsTypes";

interface Props {
  reconciliation: PublicReconciliation | null;
}

const PALETTE = {
  parchment: "var(--currents-parchment)",
  muted: "var(--currents-muted)",
  amber: "var(--currents-amber)",
};

function summaryLabel(reconciliation: PublicReconciliation): string {
  if (reconciliation.no_counter_found) {
    return "No canonical counter-claim found in firm history";
  }
  if (reconciliation.unresolved_tension) {
    return "Unresolved tension with firm history";
  }
  return "Where this could be wrong";
}

function counterCaption(reconciliation: PublicReconciliation): string | null {
  const counter = reconciliation.counter_claim;
  if (!counter) return null;
  const title =
    counter.conclusion_title?.trim() ||
    counter.conclusion_text?.trim() ||
    counter.quoted_span?.trim() ||
    counter.source_id;
  const trimmed = title.length > 200 ? `${title.slice(0, 197)}...` : title;
  return `Counter-claim: ${trimmed}`;
}

export default function CurrentsReconciliation({ reconciliation }: Props) {
  const initiallyOpen = Boolean(reconciliation?.unresolved_tension);
  const [open, setOpen] = useState<boolean>(initiallyOpen);

  if (!reconciliation) return null;

  const label = summaryLabel(reconciliation);
  const counter = reconciliation.counter_claim;
  const caption = counterCaption(reconciliation);

  return (
    <section
      aria-label="Where this could be wrong"
      style={{
        border: `1px solid ${
          reconciliation.unresolved_tension ? PALETTE.amber : "rgba(255,255,255,0.12)"
        }`,
        borderRadius: "0.4rem",
        marginTop: "1.5rem",
        overflow: "hidden",
      }}
    >
      <button
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        style={{
          alignItems: "center",
          background: "transparent",
          border: 0,
          color: PALETTE.parchment,
          cursor: "pointer",
          display: "flex",
          fontFamily: "'Cinzel', serif",
          fontSize: "0.85rem",
          gap: "0.6rem",
          justifyContent: "space-between",
          letterSpacing: "0.08em",
          padding: "0.85rem 1rem",
          textAlign: "left",
          textTransform: "uppercase",
          width: "100%",
        }}
      >
        <span>{label}</span>
        <span aria-hidden style={{ color: PALETTE.muted, fontFamily: "monospace" }}>
          {open ? "[hide]" : "[show]"}
        </span>
      </button>
      {open ? (
        <div
          style={{
            borderTop: "1px solid rgba(255,255,255,0.08)",
            display: "grid",
            gap: "0.7rem",
            padding: "1rem",
          }}
        >
          {caption ? (
            <p
              style={{
                color: PALETTE.muted,
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: "0.78rem",
                lineHeight: 1.5,
                margin: 0,
              }}
            >
              {counter?.public_url ? (
                <a
                  href={counter.public_url}
                  style={{ color: PALETTE.amber, textDecoration: "underline" }}
                >
                  {caption}
                </a>
              ) : (
                caption
              )}
            </p>
          ) : null}
          <p
            style={{
              color: PALETTE.parchment,
              fontSize: "1rem",
              lineHeight: 1.65,
              margin: 0,
            }}
          >
            {reconciliation.reconciliation_markdown}
          </p>
          {reconciliation.unresolved_tension &&
          reconciliation.what_we_would_need_to_know ? (
            <p
              style={{
                borderLeft: `3px solid ${PALETTE.amber}`,
                color: PALETTE.amber,
                fontSize: "0.94rem",
                lineHeight: 1.55,
                margin: 0,
                paddingLeft: "0.85rem",
              }}
            >
              <strong style={{ marginRight: "0.4rem" }}>What we&apos;d need to know:</strong>
              {reconciliation.what_we_would_need_to_know}
            </p>
          ) : null}
          {!reconciliation.no_counter_found &&
          reconciliation.strongest_form_of_counter_claim ? (
            <details
              style={{
                color: PALETTE.muted,
                fontSize: "0.85rem",
                lineHeight: 1.5,
              }}
            >
              <summary style={{ cursor: "pointer" }}>
                Strongest form of the counter-claim
              </summary>
              <p style={{ margin: "0.4rem 0 0" }}>
                {reconciliation.strongest_form_of_counter_claim}
              </p>
            </details>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
