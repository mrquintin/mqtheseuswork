"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import {
  driftColor,
  driftLabel,
  type ManifestMethod,
} from "@/lib/methodologyManifestShared";

type SortKey =
  | "name"
  | "status"
  | "domain"
  | "conclusions"
  | "slope"
  | "drift"
  | "review";
type SortDir = "asc" | "desc";

type Props = {
  methods: ManifestMethod[];
};

/**
 * Sortable, filterable, client-side fuzzy-searchable method index.
 *
 * Server renders the initial table from the manifest, so the
 * outsider's first paint is the full list — no flash of "loading".
 * Once hydrated, the user can search by free text, restrict by
 * domain, and re-sort. The search is a tiny token-overlap matcher;
 * we do not ship a fuzzy library because the manifest is small.
 */
export default function MethodologyIndexTable({ methods }: Props) {
  const [query, setQuery] = useState("");
  const [domainFilter, setDomainFilter] = useState<string>("__all__");
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({
    key: "name",
    dir: "asc",
  });

  const domains = useMemo(() => {
    const set = new Set<string>();
    for (const m of methods) {
      if (m.domain && m.domain.trim()) set.add(m.domain);
    }
    return Array.from(set).sort();
  }, [methods]);

  const tokens = useMemo(
    () =>
      query
        .toLowerCase()
        .split(/\s+/)
        .map((t) => t.trim())
        .filter((t) => t.length > 1),
    [query],
  );

  const visible = useMemo(() => {
    const filtered = methods.filter((m) => {
      if (domainFilter !== "__all__" && m.domain !== domainFilter) return false;
      if (tokens.length === 0) return true;
      const hay = `${m.name} ${m.description} ${m.domain ?? ""} ${m.status}`.toLowerCase();
      return tokens.every((t) => hay.includes(t));
    });
    const cmp = (a: ManifestMethod, b: ManifestMethod): number => {
      const dir = sort.dir === "asc" ? 1 : -1;
      switch (sort.key) {
        case "name":
          return a.name.localeCompare(b.name) * dir;
        case "status":
          if (a.status === b.status) return a.name.localeCompare(b.name);
          return a.status.localeCompare(b.status) * dir;
        case "domain":
          return (a.domain ?? "").localeCompare(b.domain ?? "") * dir;
        case "conclusions":
          return (a.conclusionsProduced - b.conclusionsProduced) * dir;
        case "slope": {
          const av = a.calibration?.slope ?? -Infinity;
          const bv = b.calibration?.slope ?? -Infinity;
          if (av === bv) return a.name.localeCompare(b.name);
          return (av - bv) * dir;
        }
        case "drift": {
          const order = { ok: 0, warn: 1, escalate: 2 } as const;
          return (order[a.drift.state] - order[b.drift.state]) * dir;
        }
        case "review": {
          const av = a.lastReviewDate ? new Date(a.lastReviewDate).getTime() : 0;
          const bv = b.lastReviewDate ? new Date(b.lastReviewDate).getTime() : 0;
          return (av - bv) * dir;
        }
      }
    };
    return [...filtered].sort(cmp);
  }, [methods, domainFilter, tokens, sort]);

  const onHeaderClick = (key: SortKey) => {
    setSort((prev) => ({
      key,
      dir: prev.key === key ? (prev.dir === "asc" ? "desc" : "asc") : "asc",
    }));
  };

  const arrow = (key: SortKey) =>
    sort.key === key ? (sort.dir === "asc" ? " ↑" : " ↓") : "";

  return (
    <div>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.75rem",
          alignItems: "center",
          marginBottom: "1rem",
        }}
      >
        <label
          className="mono"
          style={{
            fontSize: "0.65rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--public-muted, #888)",
          }}
        >
          Search
          <input
            aria-label="Search methods"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. coherence, contradiction"
            style={{
              marginLeft: "0.5rem",
              padding: "0.35rem 0.55rem",
              border: "1px solid var(--public-rule, #ccc)",
              borderRadius: 2,
              fontFamily: "inherit",
              fontSize: "0.9rem",
              minWidth: 220,
              background: "transparent",
              color: "inherit",
            }}
          />
        </label>
        {domains.length > 0 ? (
          <label
            className="mono"
            style={{
              fontSize: "0.65rem",
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: "var(--public-muted, #888)",
            }}
          >
            Domain
            <select
              aria-label="Filter by domain"
              value={domainFilter}
              onChange={(e) => setDomainFilter(e.target.value)}
              style={{
                marginLeft: "0.5rem",
                padding: "0.35rem 0.55rem",
                border: "1px solid var(--public-rule, #ccc)",
                borderRadius: 2,
                fontFamily: "inherit",
                fontSize: "0.9rem",
                background: "transparent",
                color: "inherit",
              }}
            >
              <option value="__all__">All domains</option>
              {domains.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <span
          className="public-muted"
          style={{ fontSize: "0.78rem", marginLeft: "auto" }}
        >
          {visible.length} of {methods.length} methods
        </span>
      </div>

      <table
        className="public-table"
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "0.9rem",
        }}
      >
        <thead>
          <tr style={{ textAlign: "left", color: "var(--public-muted, #888)" }}>
            <Th onClick={() => onHeaderClick("name")}>
              Method{arrow("name")}
            </Th>
            <th style={thBaseStyle()}>Description</th>
            <Th onClick={() => onHeaderClick("status")}>
              Status{arrow("status")}
            </Th>
            <Th onClick={() => onHeaderClick("domain")}>
              Domain{arrow("domain")}
            </Th>
            <Th onClick={() => onHeaderClick("conclusions")}>
              Conclusions{arrow("conclusions")}
            </Th>
            <Th onClick={() => onHeaderClick("slope")}>
              Cal. slope{arrow("slope")}
            </Th>
            <Th onClick={() => onHeaderClick("drift")}>
              Drift{arrow("drift")}
            </Th>
            <Th onClick={() => onHeaderClick("review")}>
              Last review{arrow("review")}
            </Th>
          </tr>
        </thead>
        <tbody>
          {visible.length === 0 ? (
            <tr>
              <td
                colSpan={8}
                className="public-muted"
                style={{ padding: "1rem 0.75rem", fontStyle: "italic" }}
              >
                No methods match this filter.
              </td>
            </tr>
          ) : (
            visible.map((m) => (
              <tr
                key={m.name}
                className="public-table-row"
                style={{ borderTop: "1px solid var(--public-rule, #ddd)" }}
              >
                <td
                  data-label="Method"
                  style={{
                    padding: "0.55rem 0.75rem 0.55rem 0",
                    fontFamily: "monospace",
                    whiteSpace: "nowrap",
                  }}
                >
                  <Link
                    href={`/methodology/${encodeURIComponent(m.name)}`}
                    style={{ fontWeight: 600 }}
                  >
                    {m.name}
                  </Link>
                  <div
                    className="public-muted"
                    style={{ fontSize: "0.7rem", marginTop: 2 }}
                  >
                    v{m.version}
                  </div>
                </td>
                <td
                  data-label="Description"
                  style={{ padding: "0.55rem 0.75rem", maxWidth: 360 }}
                >
                  {m.description}
                </td>
                <td data-label="Status" style={{ padding: "0.55rem 0.75rem" }}>
                  <StatusPill status={m.status} />
                </td>
                <td
                  data-label="Domain"
                  style={{
                    padding: "0.55rem 0.75rem",
                    color: m.domain ? undefined : "var(--public-muted, #888)",
                  }}
                >
                  {m.domain || "—"}
                </td>
                <td
                  data-label="Conclusions"
                  style={{ padding: "0.55rem 0.75rem" }}
                >
                  {m.conclusionsProduced}
                </td>
                <td
                  data-label="Cal. slope"
                  style={{ padding: "0.55rem 0.75rem" }}
                >
                  {renderSlope(m)}
                </td>
                <td data-label="Drift" style={{ padding: "0.55rem 0.75rem" }}>
                  <DriftPill state={m.drift.state} />
                </td>
                <td
                  data-label="Last review"
                  style={{
                    padding: "0.55rem 0.75rem",
                    color: "var(--public-muted, #888)",
                    fontSize: "0.82rem",
                  }}
                >
                  {m.lastReviewDate ? m.lastReviewDate.slice(0, 10) : "—"}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function thBaseStyle(): React.CSSProperties {
  return {
    padding: "0.5rem 0.75rem",
    fontWeight: 400,
    textAlign: "left",
  };
}

function Th({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <th style={thBaseStyle()}>
      <button
        type="button"
        onClick={onClick}
        style={{
          background: "transparent",
          border: 0,
          padding: 0,
          cursor: "pointer",
          color: "inherit",
          font: "inherit",
          letterSpacing: "0.04em",
        }}
      >
        {children}
      </button>
    </th>
  );
}

/**
 * Slope cell. Precision audit (Explorer v2): a calibration slope is a
 * regression coefficient near 1.0 — two decimals is the precision the
 * bootstrap actually supports, and the CI bounds are held to the same
 * two places. Nothing in this table is rendered at raw float width.
 */
function renderSlope(m: ManifestMethod): React.ReactNode {
  const cal = m.calibration;
  if (!cal) {
    return (
      <span className="public-muted" title="Sample size below publish gate.">
        —
      </span>
    );
  }
  return (
    <span title={`n=${cal.sampleSize}${cal.domain ? ` · ${cal.domain}` : ""}`}>
      {cal.slope.toFixed(2)}
      {cal.ciLow !== null && cal.ciHigh !== null ? (
        <span
          className="public-muted"
          style={{ marginLeft: 4, fontSize: "0.78rem" }}
        >
          [{cal.ciLow.toFixed(2)}, {cal.ciHigh.toFixed(2)}]
        </span>
      ) : null}
    </span>
  );
}

const STATUS_COLOR: Record<string, string> = {
  active: "var(--public-muted, #888)",
  deprecated: "var(--ember, #c0392b)",
  experimental: "var(--amber, #d4a017)",
};

function StatusPill({ status }: { status: string }) {
  const color = STATUS_COLOR[status] ?? "var(--public-muted, #888)";
  return (
    <span
      style={{
        display: "inline-block",
        padding: "0.12rem 0.45rem",
        border: `1px solid ${color}`,
        color,
        fontFamily: "monospace",
        fontSize: "0.62rem",
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        whiteSpace: "nowrap",
      }}
    >
      {status || "—"}
    </span>
  );
}

function DriftPill({ state }: { state: ManifestMethod["drift"]["state"] }) {
  const label = driftLabel(state);
  const color = driftColor(state);
  return (
    <span
      style={{
        display: "inline-block",
        padding: "0.12rem 0.45rem",
        border: `1px solid ${color}`,
        color,
        fontFamily: "monospace",
        fontSize: "0.62rem",
        letterSpacing: "0.18em",
        textTransform: "uppercase",
      }}
    >
      {label}
    </span>
  );
}
