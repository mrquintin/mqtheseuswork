import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import MethodTabs from "@/components/MethodTabs";
import PublicHeader from "@/components/PublicHeader";
import { db } from "@/lib/db";
import { getFounder } from "@/lib/auth";
import {
  MIN_PUBLISHABLE_SAMPLE,
  describeConfidenceBand,
  formatSlopeCi,
  type MethodTrackRecordRow,
} from "@/lib/methodTrackRecord";

export const metadata: Metadata = {
  title: "Method track record",
};

function decimalToNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string") {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  if (typeof value === "object" && "toNumber" in (value as object)) {
    try {
      const n = (value as { toNumber: () => number }).toNumber();
      return Number.isFinite(n) ? n : null;
    } catch {
      return null;
    }
  }
  return null;
}

/**
 * Public track-record page for a method, addressed by `[method]` (the
 * method `name` field — versions roll up). The publish gate is a hard
 * filter: rows below `MIN_PUBLISHABLE_SAMPLE` are excluded, and if no
 * row clears the threshold the page returns 404 rather than rendering
 * a "no data" placeholder. The intent is that the page exists when —
 * and only when — there are enough resolved predictions linked to the
 * method to publish a record honestly.
 *
 * Multi-tenant note: track records are materialized per-org. The public
 * page picks the largest-sample row per (version, domain) across all
 * orgs that have published a track record for this method. The
 * organization id is not exposed in the public surface — the reader
 * sees only the method's empirical record.
 */
export default async function PublicMethodTrackRecordPage({
  params,
}: {
  params: Promise<{ method: string }>;
}) {
  const { method } = await params;
  const methodName = decodeURIComponent(method);

  const rawRows = await db.methodTrackRecord.findMany({
    where: { methodName },
    orderBy: [{ methodVersion: "desc" }, { sampleSize: "desc" }],
  });

  const rows: MethodTrackRecordRow[] = rawRows.map((r) => ({
    organizationId: r.organizationId,
    methodName: r.methodName,
    methodVersion: r.methodVersion,
    domain: r.domain,
    sampleSize: r.sampleSize,
    weightedBrier: decimalToNumber(r.weightedBrier),
    calibrationSlope: decimalToNumber(r.calibrationSlope),
    calibrationSlopeCiLow: decimalToNumber(r.calibrationSlopeCiLow),
    calibrationSlopeCiHigh: decimalToNumber(r.calibrationSlopeCiHigh),
    severityPassRate: decimalToNumber(r.severityPassRate),
    computedAt: r.computedAt,
  }));

  // Publish gate: at least one (version, domain) cell must clear the
  // sample-size threshold. Below that we 404 — we don't publish thin
  // track records dressed up as confident ones.
  const publishable = rows.filter((r) => r.sampleSize >= MIN_PUBLISHABLE_SAMPLE);
  if (publishable.length === 0) {
    notFound();
  }

  // Pick the largest-sample row per (version, domain) so multiple orgs'
  // records collapse to one row without us silently re-aggregating
  // (which would risk smoothing across domains, breaking the contract
  // enforced by the Python aggregator).
  const byCell = new Map<string, MethodTrackRecordRow>();
  for (const r of publishable) {
    const key = `${r.methodVersion}::${r.domain}`;
    const existing = byCell.get(key);
    if (!existing || r.sampleSize > existing.sampleSize) {
      byCell.set(key, r);
    }
  }
  const visible = Array.from(byCell.values()).sort((a, b) => {
    if (a.methodVersion !== b.methodVersion) {
      return b.methodVersion.localeCompare(a.methodVersion);
    }
    return a.domain.localeCompare(b.domain);
  });

  const founder = await getFounder();

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container public-methodology-page">
        <Link href="/methodology" className="public-muted" style={{ fontSize: "0.75rem" }}>
          ← Methodology
        </Link>
        <h1 className="public-title" style={{ marginTop: "0.5rem" }}>
          Track record · <span style={{ fontFamily: "monospace" }}>{methodName}</span>
        </h1>

        <MethodTabs method={methodName} active="track-record" />

        <p className="public-muted public-lede">
          The empirical record of conclusions reached using this method —
          calibration slope, weighted Brier, and severity-pass rate, with a
          90% bootstrap confidence band on the slope. Methods are only
          listed publicly once the track record clears n ≥{" "}
          {MIN_PUBLISHABLE_SAMPLE}.
        </p>

        <table
          className="public-table"
          style={{
            width: "100%",
            borderCollapse: "collapse",
            marginTop: "1.5rem",
            fontSize: "0.9rem",
          }}
        >
          <thead>
            <tr style={{ textAlign: "left", color: "var(--public-muted, #888)" }}>
              <th style={{ padding: "0.5rem 0.75rem 0.5rem 0", fontWeight: 400 }}>
                Version
              </th>
              <th style={{ padding: "0.5rem 0.75rem", fontWeight: 400 }}>Domain</th>
              <th style={{ padding: "0.5rem 0.75rem", fontWeight: 400 }}>n</th>
              <th style={{ padding: "0.5rem 0.75rem", fontWeight: 400 }}>
                Weighted Brier
              </th>
              <th style={{ padding: "0.5rem 0.75rem", fontWeight: 400 }}>
                Calibration slope
              </th>
              <th style={{ padding: "0.5rem 0.75rem", fontWeight: 400 }}>
                90% CI
              </th>
              <th style={{ padding: "0.5rem 0.75rem", fontWeight: 400 }}>
                Severity pass
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr
                key={`${row.methodVersion}-${row.domain}`}
                style={{ borderTop: "1px solid var(--public-rule, #ddd)" }}
              >
                <td style={{ padding: "0.5rem 0.75rem 0.5rem 0", fontFamily: "monospace" }}>
                  v{row.methodVersion}
                </td>
                <td style={{ padding: "0.5rem 0.75rem" }}>
                  {row.domain || <span className="public-muted">—</span>}
                </td>
                <td style={{ padding: "0.5rem 0.75rem" }}>{row.sampleSize}</td>
                <td style={{ padding: "0.5rem 0.75rem" }}>
                  {row.weightedBrier !== null
                    ? row.weightedBrier.toFixed(3)
                    : "—"}
                </td>
                <td style={{ padding: "0.5rem 0.75rem" }}>
                  {row.calibrationSlope !== null
                    ? row.calibrationSlope.toFixed(2)
                    : "—"}
                </td>
                <td style={{ padding: "0.5rem 0.75rem" }}>{formatSlopeCi(row)}</td>
                <td style={{ padding: "0.5rem 0.75rem" }}>
                  {row.severityPassRate !== null
                    ? `${Math.round(row.severityPassRate * 100)}%`
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <ul
          className="public-muted"
          style={{ marginTop: "1.5rem", paddingLeft: "1rem", fontSize: "0.8rem" }}
        >
          {visible.map((row) => (
            <li
              key={`note-${row.methodVersion}-${row.domain || "_"}`}
              style={{ marginBottom: "0.25rem" }}
            >
              v{row.methodVersion}
              {row.domain ? ` · ${row.domain}` : ""}: {describeConfidenceBand(row)}
            </li>
          ))}
        </ul>
      </main>
    </>
  );
}
