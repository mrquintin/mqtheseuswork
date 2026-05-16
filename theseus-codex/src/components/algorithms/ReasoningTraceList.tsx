"use client";

import Link from "next/link";
import { useState } from "react";

import type { AlgorithmReasoningStep } from "@/lib/algorithmsApi";

/**
 * Central audit component. Renders an invocation's reasoning trace as
 * a numbered list of step rows. Each row labels its kind, summarises
 * the carried fact, and — for `APPLY_PRINCIPLE` steps — exposes the
 * principle text inline as a collapsible.
 *
 * The component accepts both forms the runtime emits:
 *   - the structured `reasoning_chain` definition on the algorithm
 *     itself (used by the "how this algorithm works" section of the
 *     detail page);
 *   - the flattened `reasoning_trace` list of strings the runtime
 *     persists onto each invocation (used by the invocation drill).
 *
 * Pass `principleTextsById` to inline the principle text for
 * `APPLY_PRINCIPLE` steps; without it, the principle id is shown as a
 * link to `/principles/<id>`.
 */

export type ReasoningTraceListProps = {
  chain?: AlgorithmReasoningStep[];
  traceLines?: string[];
  principleTextsById?: Record<string, string>;
};

type ParsedTraceLine = {
  kind: "DETECT" | "APPLY_PRINCIPLE" | "SYNTHESIZE" | "OUTPUT";
  principleId: string | null;
  body: string;
};

function parseTraceLine(line: string): ParsedTraceLine {
  const trimmed = line.trim();
  if (trimmed.startsWith("APPLY_PRINCIPLE(")) {
    const closeIdx = trimmed.indexOf(")");
    if (closeIdx > 16) {
      const principleId = trimmed.slice("APPLY_PRINCIPLE(".length, closeIdx);
      const rest = trimmed.slice(closeIdx + 1).replace(/^:\s*/, "");
      return { kind: "APPLY_PRINCIPLE", principleId, body: rest };
    }
  }
  for (const kind of ["DETECT", "APPLY_PRINCIPLE", "SYNTHESIZE", "OUTPUT"] as const) {
    const prefix = `${kind}:`;
    if (trimmed.startsWith(prefix)) {
      return { kind, principleId: null, body: trimmed.slice(prefix.length).trim() };
    }
  }
  return { kind: "DETECT", principleId: null, body: trimmed };
}

const KIND_LABEL: Record<ParsedTraceLine["kind"], string> = {
  DETECT: "observed",
  APPLY_PRINCIPLE: "applied principle",
  SYNTHESIZE: "synthesised",
  OUTPUT: "final output",
};

const KIND_COLOR: Record<ParsedTraceLine["kind"], string> = {
  DETECT: "var(--public-muted, #888)",
  APPLY_PRINCIPLE: "var(--amber, #d4a017)",
  SYNTHESIZE: "rgba(160, 211, 170, 0.9)",
  OUTPUT: "rgba(176, 196, 222, 0.95)",
};

function PrincipleInline({
  principleId,
  text,
}: {
  principleId: string;
  text?: string;
}) {
  const [open, setOpen] = useState(false);
  if (!text) {
    return (
      <Link
        href={`/principles/${principleId}`}
        style={{
          color: "var(--amber, #d4a017)",
          textDecoration: "underline",
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: "0.75rem",
        }}
      >
        principle {principleId.slice(0, 12)}
      </Link>
    );
  }
  return (
    <span style={{ display: "inline-flex", alignItems: "baseline", gap: "0.4rem" }}>
      <button
        type="button"
        data-testid="principle-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{
          background: "transparent",
          border: "none",
          color: "var(--amber, #d4a017)",
          cursor: "pointer",
          padding: 0,
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: "0.75rem",
        }}
      >
        {open ? "▾" : "▸"} principle
      </button>
      <Link
        href={`/principles/${principleId}`}
        style={{
          color: "var(--public-muted, #888)",
          textDecoration: "underline",
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: "0.7rem",
        }}
      >
        {principleId.slice(0, 12)}
      </Link>
      {open ? (
        <span
          style={{
            display: "block",
            marginTop: "0.4rem",
            paddingLeft: "0.75rem",
            borderLeft: "2px solid var(--amber, #d4a017)",
            fontFamily: "'EB Garamond', serif",
            fontSize: "0.95rem",
            lineHeight: 1.5,
            color: "var(--text, #ddd)",
          }}
        >
          {text}
        </span>
      ) : null}
    </span>
  );
}

function structuredItems(
  chain: AlgorithmReasoningStep[],
): Array<{
  kind: ParsedTraceLine["kind"];
  principleId: string | null;
  body: string;
  predicate: string | null;
}> {
  return chain.map((step) => ({
    kind: step.step_kind as ParsedTraceLine["kind"],
    principleId: step.principle_id,
    body: step.derived_fact ?? "",
    predicate: step.predicate ?? null,
  }));
}

function traceItems(
  lines: string[],
): Array<{
  kind: ParsedTraceLine["kind"];
  principleId: string | null;
  body: string;
  predicate: string | null;
}> {
  return lines.map((line) => {
    const parsed = parseTraceLine(line);
    return { ...parsed, predicate: null };
  });
}

export default function ReasoningTraceList({
  chain,
  traceLines,
  principleTextsById,
}: ReasoningTraceListProps) {
  const items = traceLines && traceLines.length > 0
    ? traceItems(traceLines)
    : chain
      ? structuredItems(chain)
      : [];
  if (items.length === 0) {
    return (
      <p
        data-testid="reasoning-trace-empty"
        style={{ color: "var(--public-muted, #888)", margin: 0 }}
      >
        No reasoning steps recorded.
      </p>
    );
  }
  return (
    <ol
      data-testid="reasoning-trace"
      style={{
        listStyle: "none",
        padding: 0,
        margin: 0,
        display: "flex",
        flexDirection: "column",
        gap: "0.65rem",
        counterReset: "step",
      }}
    >
      {items.map((item, idx) => (
        <li
          key={idx}
          data-step-kind={item.kind}
          data-testid="reasoning-step"
          style={{
            display: "flex",
            gap: "0.85rem",
            padding: "0.65rem 0.8rem",
            border: `1px solid var(--border, #333)`,
            borderLeft: `3px solid ${KIND_COLOR[item.kind]}`,
            background: "var(--stone-light, #1d1d1d)",
            borderRadius: 3,
          }}
        >
          <span
            aria-hidden="true"
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              color: "var(--public-muted, #888)",
              fontSize: "0.7rem",
              minWidth: "1.5rem",
              textAlign: "right",
            }}
          >
            {String(idx + 1).padStart(2, "0")}
          </span>
          <div style={{ flex: 1 }}>
            <div
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: "0.6rem",
                letterSpacing: "0.22em",
                textTransform: "uppercase",
                color: KIND_COLOR[item.kind],
                marginBottom: "0.25rem",
              }}
            >
              {KIND_LABEL[item.kind]}
            </div>
            {item.predicate ? (
              <div
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: "0.78rem",
                  color: "var(--public-muted, #aaa)",
                  marginBottom: "0.3rem",
                }}
              >
                predicate: {item.predicate}
              </div>
            ) : null}
            {item.body ? (
              <div
                style={{
                  fontFamily: "'EB Garamond', serif",
                  fontSize: "1rem",
                  lineHeight: 1.55,
                }}
              >
                {item.body}
              </div>
            ) : null}
            {item.kind === "APPLY_PRINCIPLE" && item.principleId ? (
              <div style={{ marginTop: "0.4rem" }}>
                <PrincipleInline
                  principleId={item.principleId}
                  text={principleTextsById?.[item.principleId]}
                />
              </div>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
