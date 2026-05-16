import Link from "next/link";

import type { PublicInvocationRow } from "@/lib/algorithmsPublicApi";

/**
 * Compact table of recent invocations on the algorithm detail page.
 *
 * Renders unresolved and resolved rows side by side — institutional
 * honesty per the round directive: do not hide the unflattering
 * outcomes. The correctness column shows a dash for the unresolved
 * rows so the founder can see the gap.
 */

export type InvocationTableProps = {
  algorithmId: string;
  invocations: PublicInvocationRow[];
};

const CORRECTNESS_COLOR: Record<string, string> = {
  CORRECT: "rgba(160, 211, 170, 0.95)",
  PARTIALLY_CORRECT: "var(--amber, #d4a017)",
  INCORRECT: "var(--ember, #c0584a)",
  INDETERMINATE: "var(--public-muted, #888)",
};

function formatOutput(payload: Record<string, unknown>): string {
  const keys = Object.keys(payload);
  if (keys.length === 0) return "(no output)";
  if (keys.length === 1) {
    const v = payload[keys[0]];
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      return `${keys[0]}=${v}`;
    }
  }
  try {
    const compact = JSON.stringify(payload);
    return compact.length > 80 ? `${compact.slice(0, 77)}…` : compact;
  } catch {
    return "(opaque output)";
  }
}

function formatDate(date: Date): string {
  try {
    return date.toISOString().replace("T", " ").slice(0, 19);
  } catch {
    return String(date);
  }
}

export default function InvocationTable({ algorithmId, invocations }: InvocationTableProps) {
  if (invocations.length === 0) {
    return (
      <p
        data-testid="invocation-table-empty"
        style={{ color: "var(--public-muted, #888)", margin: 0 }}
      >
        No invocations recorded yet.
      </p>
    );
  }
  return (
    <div
      data-testid="invocation-table"
      style={{ overflowX: "auto", border: "1px solid var(--border, #333)", borderRadius: 3 }}
    >
      <table
        style={{
          borderCollapse: "collapse",
          width: "100%",
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: "0.78rem",
        }}
      >
        <thead>
          <tr style={{ textAlign: "left", color: "var(--public-muted, #888)" }}>
            <th style={thStyle}>fired</th>
            <th style={thStyle}>output</th>
            <th style={thStyle}>conf.</th>
            <th style={thStyle}>resolved</th>
            <th style={thStyle}>correctness</th>
            <th style={thStyle}></th>
          </tr>
        </thead>
        <tbody>
          {invocations.map((inv) => (
            <tr
              key={inv.id}
              data-testid="invocation-row"
              style={{ borderTop: "1px solid var(--border, #333)" }}
            >
              <td style={tdStyle}>{formatDate(inv.invokedAt)}</td>
              <td style={tdStyle}>{formatOutput(inv.derivedOutput)}</td>
              <td style={tdStyle}>
                {inv.confidenceLow.toFixed(2)} – {inv.confidenceHigh.toFixed(2)}
              </td>
              <td style={tdStyle}>{inv.resolvedAt ? formatDate(inv.resolvedAt) : "—"}</td>
              <td
                style={{
                  ...tdStyle,
                  color: inv.correctness ? CORRECTNESS_COLOR[inv.correctness] : "var(--public-muted, #888)",
                }}
              >
                {inv.correctness ?? "unresolved"}
              </td>
              <td style={tdStyle}>
                <Link
                  href={`/algorithms/${algorithmId}/invocations/${inv.id}`}
                  style={{
                    color: "var(--amber, #d4a017)",
                    textDecoration: "none",
                  }}
                >
                  drill →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const thStyle: React.CSSProperties = {
  padding: "0.5rem 0.75rem",
  fontSize: "0.55rem",
  letterSpacing: "0.22em",
  textTransform: "uppercase",
  fontWeight: 400,
};

const tdStyle: React.CSSProperties = {
  padding: "0.55rem 0.75rem",
  verticalAlign: "top",
};
