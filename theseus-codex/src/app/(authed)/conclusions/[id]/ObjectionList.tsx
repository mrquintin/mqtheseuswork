"use client";

import { useState } from "react";
import type { Finding, PeerReviewRecord } from "@/lib/api/round3";
import {
  objectionSeverityColor,
  objectionSeverityRank,
} from "@/lib/colors";

const DEFAULT_TOP_K = 3;

type SeverityLabel = "low" | "medium" | "high";

interface ParsedSeverity {
  label: SeverityLabel;
  value: number;
  judgeCapped: boolean;
  stale: boolean;
}

interface FlatObjection {
  recordId: string;
  reviewerName: string;
  index: number;
  finding: Finding;
  severity: ParsedSeverity | null;
}

function parseSeverity(finding: Finding): ParsedSeverity | null {
  let label: SeverityLabel | null = null;
  let value = 0;
  let judgeCapped = false;
  let stale = false;
  for (const ev of finding.evidence || []) {
    if (ev.startsWith("severity=") && ev.includes(":")) {
      const [, rest] = ev.split("=", 2);
      const [labelStr, valStr] = rest.split(":", 2);
      if (labelStr === "low" || labelStr === "medium" || labelStr === "high") {
        label = labelStr;
        const n = Number(valStr);
        if (!Number.isNaN(n)) value = n;
      }
    } else if (ev === "severity_judge_capped=true") {
      judgeCapped = true;
    } else if (ev === "severity_stale=true") {
      stale = true;
    }
  }
  if (!label) return null;
  return { label, value, judgeCapped, stale };
}

function flatten(records: PeerReviewRecord[]): FlatObjection[] {
  const out: FlatObjection[] = [];
  for (const r of records || []) {
    (r.findings || []).forEach((f, i) => {
      // Only objections — drop info-level provider-error rows so the
      // top-K view isn't padded with infrastructure noise.
      if (f.severity === "info") return;
      out.push({
        recordId: r.id,
        reviewerName: r.reviewerName,
        index: i,
        finding: f,
        severity: parseSeverity(f),
      });
    });
  }
  return out;
}

function sortBySeverity(items: FlatObjection[]): FlatObjection[] {
  return [...items].sort((a, b) => {
    // Stale severities sink to the bottom regardless of value — they
    // are no longer load-bearing on the current conclusion.
    const sa = a.severity && !a.severity.stale ? a.severity : null;
    const sb = b.severity && !b.severity.stale ? b.severity : null;
    const ra = sa ? objectionSeverityRank(sa.label) : -1;
    const rb = sb ? objectionSeverityRank(sb.label) : -1;
    if (ra !== rb) return rb - ra;
    return (sb?.value ?? 0) - (sa?.value ?? 0);
  });
}

export interface ObjectionListProps {
  records: PeerReviewRecord[];
  topK?: number;
}

/**
 * Severity-ordered objection list for the conclusion detail page.
 *
 * Shows only the top-K severity objections by default; "Show all"
 * expands to the full list. Severity rendered as a colored bar so the
 * scan picks up structural blows over nitpicks at a glance.
 */
export default function ObjectionList({
  records,
  topK = DEFAULT_TOP_K,
}: ObjectionListProps) {
  const [expanded, setExpanded] = useState(false);

  const all = sortBySeverity(flatten(records));
  if (all.length === 0) {
    return (
      <p style={{ color: "var(--parchment-dim)", fontSize: "0.8rem" }}>
        No scored objections.
      </p>
    );
  }

  const visible = expanded ? all : all.slice(0, topK);
  const hidden = all.length - visible.length;

  const responseRequired = all.filter(
    (o) => o.severity?.label === "high" && !o.severity.stale,
  ).length;
  const responseRecommended = all.filter(
    (o) => o.severity?.label === "medium" && !o.severity.stale,
  ).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      {(responseRequired > 0 || responseRecommended > 0) && (
        <div
          style={{
            fontSize: "0.7rem",
            color: "var(--parchment-dim)",
          }}
        >
          {responseRequired > 0 && (
            <span style={{ color: "var(--ember)" }}>
              {responseRequired} high-severity objection
              {responseRequired === 1 ? "" : "s"} require a response before
              publication.
            </span>
          )}
          {responseRequired > 0 && responseRecommended > 0 && " "}
          {responseRecommended > 0 && (
            <span style={{ color: "var(--amber)" }}>
              {responseRecommended} medium-severity objection
              {responseRecommended === 1 ? "" : "s"} would benefit from a
              response.
            </span>
          )}
        </div>
      )}

      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "flex",
          flexDirection: "column",
          gap: "0.4rem",
        }}
      >
        {visible.map((o) => (
          <ObjectionRow
            key={`${o.recordId}:${o.index}`}
            objection={o}
          />
        ))}
      </ul>

      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          style={{
            alignSelf: "flex-start",
            background: "transparent",
            border: "1px solid var(--gold-dim)",
            color: "var(--gold)",
            padding: "0.25rem 0.7rem",
            fontSize: "0.7rem",
            cursor: "pointer",
            letterSpacing: "0.08em",
          }}
        >
          Show all ({hidden} more)
        </button>
      )}
      {expanded && all.length > topK && (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          style={{
            alignSelf: "flex-start",
            background: "transparent",
            border: "1px solid var(--parchment-dim)",
            color: "var(--parchment-dim)",
            padding: "0.25rem 0.7rem",
            fontSize: "0.7rem",
            cursor: "pointer",
            letterSpacing: "0.08em",
          }}
        >
          Show only top {topK}
        </button>
      )}
    </div>
  );
}

function ObjectionRow({ objection }: { objection: FlatObjection }) {
  const sev = objection.severity;
  const color = sev ? objectionSeverityColor(sev.label) : "var(--parchment-dim)";
  return (
    <li
      style={{
        padding: "0.5rem 0.75rem",
        borderLeft: `3px solid ${color}`,
        opacity: sev?.stale ? 0.55 : 1,
      }}
    >
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          alignItems: "center",
          marginBottom: "0.2rem",
        }}
      >
        <span
          style={{
            fontSize: "0.6rem",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color,
          }}
        >
          {sev ? `severity ${sev.label} ${sev.value.toFixed(2)}` : "unscored"}
          {sev?.judgeCapped ? " (judge capped)" : ""}
          {sev?.stale ? " (stale)" : ""}
        </span>
        <span style={{ fontSize: "0.6rem", color: "var(--parchment-dim)" }}>
          {objection.reviewerName}
        </span>
      </div>
      <p
        style={{
          color: "var(--parchment)",
          fontSize: "0.8rem",
          margin: 0,
          lineHeight: 1.4,
        }}
      >
        {objection.finding.detail}
      </p>
      {sev && (
        <div
          style={{
            marginTop: "0.3rem",
            height: "3px",
            background: "var(--ink-soft, rgba(255,255,255,0.08))",
            borderRadius: "2px",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${Math.round(sev.value * 100)}%`,
              height: "100%",
              background: color,
              opacity: sev.stale ? 0.4 : 1,
            }}
          />
        </div>
      )}
    </li>
  );
}
