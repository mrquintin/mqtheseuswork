import Link from "next/link";
import { fetchProvenanceForConclusionDiag } from "@/lib/api/round3";
import { requireTenantContext } from "@/lib/tenant";

/**
 * Provenance tab on the conclusion-detail page.
 *
 * Scoped to the caller's org. Uses the `Diag` variant of the fetch so
 * a missing `provenance` table (common during staged rollouts) surfaces
 * as a collapsible diagnostic rather than silently showing "no records".
 */
export default async function ProvenanceTab({ conclusionId }: { conclusionId: string }) {
  const tenant = await requireTenantContext();
  if (!tenant) return null;
  const { records, error } = await fetchProvenanceForConclusionDiag(
    tenant.organizationId,
    conclusionId,
  );

  if (records.length === 0) {
    return (
      <div style={{ padding: "0.75rem 0", color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
        No provenance records for this conclusion.
        {error && <QueryDiagnostic error={error} />}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      {records.map((r) => (
        <div key={r.id} style={{ padding: "0.75rem 1rem", borderLeft: "2px solid var(--gold-dim)" }}>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "baseline", flexWrap: "wrap" }}>
            <Link
              href={`/methods?name=${encodeURIComponent(r.extractionMethod)}`}
              style={{
                fontSize: "0.65rem",
                color: "var(--gold-dim)",
                textTransform: "uppercase",
                textDecoration: "none",
                letterSpacing: "0.05em",
              }}
              title={`View "${r.extractionMethod}" in the method registry`}
            >
              {r.extractionMethod}
            </Link>
            <span style={{ fontSize: "0.65rem", color: "var(--parchment-dim)" }}>
              · confidence {(r.confidence * 100).toFixed(0)}%
            </span>
          </div>
          {r.chain.length > 0 && (
            <div style={{ marginTop: "0.35rem", fontSize: "0.8rem" }}>
              {r.chain.map((link, i) => (
                <div key={i} style={{ color: "var(--parchment)", paddingLeft: `${link.step * 0.75}rem` }}>
                  <span style={{ color: "var(--gold-dim)" }}>{link.kind}</span> → {link.detail}
                </div>
              ))}
            </div>
          )}
          <div style={{ marginTop: "0.25rem", fontSize: "0.6rem", color: "var(--parchment-dim)" }}>
            {r.createdAt ? r.createdAt.slice(0, 10) : ""}
          </div>
        </div>
      ))}
    </div>
  );
}

function QueryDiagnostic({ error }: { error: string }) {
  return (
    <details style={{ marginTop: "0.5rem" }}>
      <summary style={{ cursor: "pointer", fontSize: "0.7rem", color: "var(--ember)" }}>
        Query diagnostic
      </summary>
      <pre
        style={{
          fontSize: "0.65rem",
          color: "var(--parchment-dim)",
          marginTop: "0.25rem",
          whiteSpace: "pre-wrap",
        }}
      >
        {error}
      </pre>
    </details>
  );
}
