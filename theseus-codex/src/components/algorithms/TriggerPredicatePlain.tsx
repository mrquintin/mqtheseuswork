"use client";

/**
 * Render a sandboxed trigger predicate as plain English.
 *
 * The runtime persists predicates as Python-flavoured boolean
 * expressions over `input.<name>` identifiers (e.g.
 * `input.escalation_index > 0.6 and input.mediator_present == False`).
 * The founder-facing surface needs the same expression rendered as
 * something a non-engineer can read at a glance:
 *
 *   "fires when escalation_index > 0.6 AND mediator_present is false"
 *
 * The renderer is intentionally light: it tokenises on the operators
 * we actually emit from the drafter (validators reject anything else
 * at promotion time), substitutes English connectives, and keeps the
 * raw predicate as a small `<details>` underneath for transparency.
 */

import { useId } from "react";

const COMPARATOR_PHRASES: Array<[RegExp, string]> = [
  [/\s+>=\s+/g, " ≥ "],
  [/\s+<=\s+/g, " ≤ "],
  [/\s+!=\s+/g, " ≠ "],
  [/\s+==\s+/g, " is "],
];

const BOOLEAN_LITERALS: Array<[RegExp, string]> = [
  [/\bTrue\b/g, "true"],
  [/\bFalse\b/g, "false"],
  [/\bNone\b/g, "null"],
];

const LOGICAL_KEYWORDS: Array<[RegExp, string]> = [
  [/\(\s*not\s+/g, "(NOT "],
  [/^\s*not\s+/g, "NOT "],
  [/\s+not\s+/g, " NOT "],
  [/\s+and\s+/g, " AND "],
  [/\s+or\s+/g, " OR "],
];

export function predicateToPlainEnglish(raw: string): string {
  if (!raw || !raw.trim()) return "always (no trigger predicate)";
  let s = raw.trim();
  // Strip the `input.` namespace — the surface already shows the
  // input slots above, and the prefix only adds noise for readers.
  s = s.replace(/\binput\.([a-zA-Z_][a-zA-Z0-9_]*)\b/g, "$1");
  for (const [pattern, replacement] of BOOLEAN_LITERALS) {
    s = s.replace(pattern, replacement);
  }
  for (const [pattern, replacement] of COMPARATOR_PHRASES) {
    s = s.replace(pattern, replacement);
  }
  for (const [pattern, replacement] of LOGICAL_KEYWORDS) {
    s = s.replace(pattern, replacement);
  }
  // Collapse the doubled spaces the substitutions sometimes leave.
  s = s.replace(/\s{2,}/g, " ").trim();
  return `fires when ${s}`;
}

export type TriggerPredicatePlainProps = {
  predicate: string;
  showRaw?: boolean;
};

export default function TriggerPredicatePlain({
  predicate,
  showRaw = true,
}: TriggerPredicatePlainProps) {
  const detailsId = useId();
  const english = predicateToPlainEnglish(predicate);
  const raw = (predicate ?? "").trim();
  return (
    <div data-testid="trigger-predicate-plain">
      <p
        style={{
          margin: 0,
          fontFamily: "'EB Garamond', serif",
          fontSize: "1rem",
          lineHeight: 1.55,
        }}
      >
        {english}
      </p>
      {showRaw && raw ? (
        <details
          id={detailsId}
          style={{
            marginTop: "0.5rem",
            fontSize: "0.7rem",
            color: "var(--public-muted, #888)",
          }}
        >
          <summary
            style={{
              cursor: "pointer",
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              fontSize: "0.6rem",
            }}
          >
            raw predicate
          </summary>
          <pre
            data-testid="trigger-predicate-raw"
            style={{
              margin: "0.4rem 0 0",
              padding: "0.5rem 0.75rem",
              border: "1px solid var(--border, #333)",
              borderRadius: 3,
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: "0.75rem",
              whiteSpace: "pre-wrap",
              wordBreak: "break-all",
            }}
          >
            {raw}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
