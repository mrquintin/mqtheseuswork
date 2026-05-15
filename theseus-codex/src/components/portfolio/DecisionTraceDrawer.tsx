"use client";

import Link from "next/link";
import type { CSSProperties } from "react";

import type { DecisionTrace } from "./types";

const drawerStyle: CSSProperties = {
  background: "rgba(16, 13, 9, 0.97)",
  border: "1px solid rgba(205, 151, 67, 0.45)",
  borderRadius: 6,
  bottom: 0,
  boxShadow: "-2px 0 18px rgba(0, 0, 0, 0.6)",
  display: "grid",
  gap: "0.85rem",
  maxWidth: 560,
  overflowY: "auto",
  padding: "1.1rem 1.2rem",
  position: "fixed",
  right: 0,
  top: 0,
  width: "100%",
  zIndex: 60,
};

const overlayStyle: CSSProperties = {
  background: "rgba(0, 0, 0, 0.45)",
  bottom: 0,
  left: 0,
  position: "fixed",
  right: 0,
  top: 0,
  zIndex: 55,
};

const sectionTitleStyle: CSSProperties = {
  color: "var(--amber)",
  fontFamily: "'Cinzel', serif",
  fontSize: "0.95rem",
  letterSpacing: "0.06em",
  margin: 0,
};

const rowStyle: CSSProperties = {
  border: "1px solid rgba(232, 225, 211, 0.12)",
  borderRadius: 4,
  display: "grid",
  gap: "0.2rem",
  padding: "0.55rem 0.7rem",
};

const labelStyle: CSSProperties = {
  color: "var(--amber-dim)",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.58rem",
  letterSpacing: "0.16em",
  textTransform: "uppercase",
};

export type DecisionTraceDrawerProps = {
  trace: DecisionTrace | null;
  isLoading?: boolean;
  error?: string | null;
  onClose: () => void;
};

export default function DecisionTraceDrawer({
  trace,
  isLoading,
  error,
  onClose,
}: DecisionTraceDrawerProps) {
  return (
    <>
      <div
        aria-hidden="true"
        data-testid="decision-trace-overlay"
        onClick={onClose}
        style={overlayStyle}
      />
      <aside
        aria-labelledby="decision-trace-title"
        data-testid="decision-trace-drawer"
        role="dialog"
        style={drawerStyle}
      >
        <header
          style={{
            alignItems: "center",
            display: "flex",
            gap: "0.5rem",
            justifyContent: "space-between",
          }}
        >
          <div>
            <h2 id="decision-trace-title" style={sectionTitleStyle}>
              Decision trace
            </h2>
            <p
              className="mono"
              style={{
                color: "var(--parchment-dim)",
                fontSize: "0.62rem",
                letterSpacing: "0.1em",
                margin: "0.15rem 0 0",
              }}
            >
              principle → signal → position → fill → resolution
            </p>
          </div>
          <button
            aria-label="Close decision trace"
            data-testid="decision-trace-close"
            onClick={onClose}
            style={closeButtonStyle}
            type="button"
          >
            ✕
          </button>
        </header>
        {isLoading ? <p style={hintStyle}>Loading trace…</p> : null}
        {error ? <p style={{ ...hintStyle, color: "var(--ember)" }}>{error}</p> : null}
        {trace ? <TraceBody trace={trace} /> : null}
      </aside>
    </>
  );
}

function TraceBody({ trace }: { trace: DecisionTrace }) {
  return (
    <div style={{ display: "grid", gap: "0.7rem" }}>
      <section style={rowStyle}>
        <span style={labelStyle}>Subject</span>
        <strong style={{ color: "var(--parchment)" }}>
          {trace.marketOrInstrumentTitle}
        </strong>
        <span
          className="mono"
          style={{ color: "var(--parchment-dim)", fontSize: "0.66rem" }}
        >
          kind={trace.kind} · position={trace.positionId}
        </span>
      </section>
      <section style={rowStyle} data-testid="decision-trace-principles">
        <span style={labelStyle}>Principles</span>
        {trace.principles.length === 0 ? (
          <span style={{ color: "var(--parchment-dim)" }}>
            (no structured principle list — see citations below)
          </span>
        ) : (
          <ul style={{ display: "grid", gap: "0.25rem", listStyle: "none", margin: 0, padding: 0 }}>
            {trace.principles.map((p) => (
              <li key={p.conclusionId}>
                <Link
                  href={`/principles/${p.conclusionId}`}
                  style={{ color: "var(--amber)", textDecoration: "none" }}
                >
                  [C:{p.conclusionId.slice(0, 8)}] {p.snippet || "(no snippet)"}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      {trace.signal ? (
        <section style={rowStyle} data-testid="decision-trace-signal">
          <span style={labelStyle}>Signal</span>
          <strong style={{ color: "var(--parchment)" }}>
            {trace.signal.headline}
          </strong>
          <span style={{ color: "var(--parchment)", fontSize: "0.84rem" }}>
            {trace.signal.directionOrSide}
            {trace.signal.confidenceLow !== null && trace.signal.confidenceHigh !== null
              ? ` · confidence ${trace.signal.confidenceLow.toFixed(2)}–${trace.signal.confidenceHigh.toFixed(2)}`
              : ""}
          </span>
        </section>
      ) : null}
      <section style={rowStyle} data-testid="decision-trace-position">
        <span style={labelStyle}>Position</span>
        <span style={{ color: "var(--parchment)" }}>
          {trace.position.mode} · {trace.position.side} · size {trace.position.size}{" "}
          @ {trace.position.entryPrice}
        </span>
        <span
          className="mono"
          style={{ color: "var(--parchment-dim)", fontSize: "0.66rem" }}
        >
          status={trace.position.status} · created {trace.position.createdAt}
        </span>
      </section>
      {trace.fill ? (
        <section style={rowStyle} data-testid="decision-trace-fill">
          <span style={labelStyle}>Fill</span>
          <span style={{ color: "var(--parchment)" }}>
            exit={trace.fill.exitPrice ?? "n/a"} · pnl=
            {trace.fill.realizedPnlUsd ?? "n/a"}
          </span>
        </section>
      ) : null}
      {trace.resolution ? (
        <section style={rowStyle} data-testid="decision-trace-resolution">
          <span style={labelStyle}>Resolution</span>
          <span style={{ color: "var(--parchment)" }}>
            outcome={trace.resolution.outcome ?? "n/a"} · brier=
            {trace.resolution.brierScore ?? "n/a"}
          </span>
          {trace.resolution.justification ? (
            <span
              style={{
                color: "var(--parchment-dim)",
                fontSize: "0.78rem",
              }}
            >
              {trace.resolution.justification}
            </span>
          ) : null}
        </section>
      ) : null}
      <section style={rowStyle} data-testid="decision-trace-citations">
        <span style={labelStyle}>Citations</span>
        {trace.citations.length === 0 ? (
          <span style={{ color: "var(--parchment-dim)" }}>(none)</span>
        ) : (
          <ul style={{ display: "grid", gap: "0.25rem", listStyle: "none", margin: 0, padding: 0 }}>
            {trace.citations.map((c, idx) => (
              <li
                key={`${c.sourceType}:${c.sourceId}:${idx}`}
                style={{ color: "var(--parchment)", fontSize: "0.78rem" }}
              >
                <span
                  className="mono"
                  style={{ color: "var(--amber-dim)", fontSize: "0.62rem" }}
                >
                  [{c.sourceType}:{c.sourceId}]
                </span>{" "}
                {c.quotedSpan}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

const hintStyle: CSSProperties = {
  color: "var(--parchment-dim)",
  fontSize: "0.82rem",
  margin: 0,
};

const closeButtonStyle: CSSProperties = {
  background: "transparent",
  border: "1px solid rgba(232, 225, 211, 0.18)",
  borderRadius: 4,
  color: "var(--parchment)",
  cursor: "pointer",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.85rem",
  height: "1.9rem",
  width: "1.9rem",
};
