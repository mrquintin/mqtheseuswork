import { redirect, notFound } from "next/navigation";
import { revalidatePath } from "next/cache";
import Link from "next/link";
import {
  fetchMethodDriftSummary,
  fetchMethodVersion,
  downloadHref,
} from "@/lib/api/round3";
import DriftPanel from "../DriftPanel";
import { requireTenantContext } from "@/lib/tenant";
import {
  describeConfidenceBand,
  fetchTrackRecordsForMethod,
  formatSlopeCi,
} from "@/lib/methodTrackRecord";

export default async function MethodVersionPage({
  params,
  searchParams,
}: {
  params: Promise<{ name: string; version: string }>;
  searchParams: Promise<{ ledger?: string }>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const { name, version } = await params;
  const decodedName = decodeURIComponent(name);
  const decodedVersion = decodeURIComponent(version);
  const sp = await searchParams;

  // Scoped: a method name registered in another org won't leak
  // through this URL — notFound() instead of returning that org's
  // version row.
  const method = await fetchMethodVersion(
    tenant.organizationId,
    decodedName,
    decodedVersion,
  );
  if (!method) notFound();

  // Track record is null when `noosphere methods track-record --rebuild`
  // has not yet run for this org/method. The card renders an empty state
  // in that case rather than failing the page.
  const trackRecords = await fetchTrackRecordsForMethod(
    tenant.organizationId,
    decodedName,
    decodedVersion,
  );

  // Drift surface is keyed on method name (not method version) — a
  // version bump does not reset the drift ledger because the upstream
  // forecasts that fed the prior version are still valid history.
  const driftSummary = await fetchMethodDriftSummary(
    tenant.organizationId,
    decodedName,
  );

  async function packageMethod() {
    "use server";
    const base = process.env.PORTAL_API_BASE || "http://localhost:3000";
    const res = await fetch(`${base}/api/round3/methods/package`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: decodedName, version: decodedVersion }),
    });
    const data = await res.json();
    revalidatePath(`/methods/${name}/${version}`);
    redirect(`/methods/${name}/${version}?ledger=${data.ledgerEntryId || "done"}`);
  }

  async function documentMethod() {
    "use server";
    const base = process.env.PORTAL_API_BASE || "http://localhost:3000";
    const res = await fetch(`${base}/api/round3/methods/document`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: decodedName, version: decodedVersion }),
    });
    const data = await res.json();
    revalidatePath(`/methods/${name}/${version}`);
    redirect(`/methods/${name}/${version}?ledger=${data.ledgerEntryId || "done"}`);
  }

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <Link href="/methods" style={{ color: "var(--gold-dim)", fontSize: "0.75rem", textDecoration: "none" }}>
        ← Back to methods
      </Link>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
          marginTop: "1rem",
        }}
      >
        {method.name}{" "}
        <span style={{ fontSize: "0.7em", color: "var(--parchment-dim)" }}>v{method.version}</span>
      </h1>

      {sp.ledger && (
        <div
          className="portal-card"
          style={{
            padding: "0.6rem 1rem",
            marginBottom: "1rem",
            borderLeft: "3px solid var(--gold)",
            fontSize: "0.8rem",
            color: "var(--gold)",
          }}
        >
          Action recorded. Ledger entry: {sp.ledger}
        </div>
      )}

      <div className="portal-card" style={{ padding: "1.25rem", marginBottom: "1.5rem" }}>
        <p style={{ color: "var(--parchment)", fontSize: "0.9rem" }}>{method.description}</p>

        {method.changelog && (
          <div style={{ marginTop: "0.75rem" }}>
            <div style={{ fontSize: "0.6rem", color: "var(--gold-dim)", textTransform: "uppercase", letterSpacing: "0.1em" }}>
              Changelog
            </div>
            <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
              {method.changelog}
            </p>
          </div>
        )}

        {Object.keys(method.parameters).length > 0 && (
          <div style={{ marginTop: "0.75rem" }}>
            <div style={{ fontSize: "0.6rem", color: "var(--gold-dim)", textTransform: "uppercase", letterSpacing: "0.1em" }}>
              Parameters
            </div>
            <pre style={{ color: "var(--parchment-dim)", fontSize: "0.75rem", marginTop: "0.25rem", overflow: "auto" }}>
              {JSON.stringify(method.parameters, null, 2)}
            </pre>
          </div>
        )}

        <div style={{ marginTop: "0.5rem", fontSize: "0.7rem", color: "var(--parchment-dim)" }}>
          Published {method.publishedAt ? method.publishedAt.slice(0, 10) : ""} by {method.publishedBy}
        </div>
      </div>

      <DriftPanel methodName={decodedName} summary={driftSummary} />

      <div className="portal-card" style={{ padding: "1.25rem", marginBottom: "1.5rem" }}>
        <div
          style={{
            fontSize: "0.6rem",
            color: "var(--gold-dim)",
            textTransform: "uppercase",
            letterSpacing: "0.1em",
            marginBottom: "0.5rem",
          }}
        >
          Track record
        </div>
        {trackRecords.length === 0 ? (
          <p style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", margin: 0 }}>
            No track-record data yet. Run{" "}
            <code style={{ color: "var(--parchment)" }}>
              noosphere methods track-record --rebuild
            </code>{" "}
            to materialize linked-conclusion outcomes for this method.
          </p>
        ) : (
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "0.8rem",
              color: "var(--parchment)",
            }}
          >
            <thead>
              <tr style={{ color: "var(--gold-dim)", textAlign: "left" }}>
                <th style={{ padding: "0.25rem 0.5rem 0.25rem 0", fontWeight: 400 }}>
                  Domain
                </th>
                <th style={{ padding: "0.25rem 0.5rem", fontWeight: 400 }}>n</th>
                <th style={{ padding: "0.25rem 0.5rem", fontWeight: 400 }}>
                  Weighted Brier
                </th>
                <th style={{ padding: "0.25rem 0.5rem", fontWeight: 400 }}>
                  Calibration slope
                </th>
                <th style={{ padding: "0.25rem 0.5rem", fontWeight: 400 }}>
                  90% CI
                </th>
                <th style={{ padding: "0.25rem 0.5rem", fontWeight: 400 }}>
                  Severity pass
                </th>
              </tr>
            </thead>
            <tbody>
              {trackRecords.map((row) => (
                <tr
                  key={`${row.methodName}-${row.methodVersion}-${row.domain}`}
                  style={{ borderTop: "1px solid var(--gold-dim)" }}
                >
                  <td style={{ padding: "0.4rem 0.5rem 0.4rem 0" }}>
                    {row.domain || <span style={{ color: "var(--parchment-dim)" }}>—</span>}
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{row.sampleSize}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>
                    {row.weightedBrier !== null
                      ? row.weightedBrier.toFixed(3)
                      : "—"}
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>
                    {row.calibrationSlope !== null
                      ? row.calibrationSlope.toFixed(2)
                      : "—"}
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>
                    {formatSlopeCi(row)}
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>
                    {row.severityPassRate !== null
                      ? `${Math.round(row.severityPassRate * 100)}%`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {trackRecords.length > 0 && (
          <ul
            style={{
              color: "var(--parchment-dim)",
              fontSize: "0.7rem",
              marginTop: "0.75rem",
              paddingLeft: "1rem",
            }}
          >
            {trackRecords.map((row) => (
              <li key={`note-${row.domain || "_"}`} style={{ marginBottom: "0.15rem" }}>
                {row.domain ? `${row.domain}: ` : ""}
                {describeConfidenceBand(row)}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <form action={packageMethod}>
          <button type="submit" className="btn-solid" style={{ fontSize: "0.65rem" }}>
            Package method
          </button>
        </form>
        <form action={documentMethod}>
          <button type="submit" className="btn-solid" style={{ fontSize: "0.65rem" }}>
            Generate docs
          </button>
        </form>
        <a
          href={downloadHref(JSON.stringify(method, null, 2), "application/json")}
          download={`method-${decodedName}-${decodedVersion}.json`}
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download JSON
        </a>
      </div>
    </main>
  );
}
