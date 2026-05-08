import { redirect } from "next/navigation";
import Link from "next/link";
import { fetchMethods, toCSV, downloadHref } from "@/lib/api/round3";
import { requireTenantContext } from "@/lib/tenant";

export default async function MethodsPage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const methods = await fetchMethods(tenant.organizationId);
  const csvData = toCSV(
    methods.map((m) => ({
      name: m.name,
      latestVersion: m.latestVersion,
      status: m.status,
      usageCount: m.usageCount,
      drift: m.driftState,
      driftLastObservedAt: m.driftLastObservedAt ?? "",
      description: m.description,
    })),
  );

  function statusColor(status: string): string {
    switch (status) {
      case "active": return "var(--gold)";
      case "candidate": return "var(--parchment)";
      case "deprecated": return "var(--parchment-dim)";
      default: return "var(--parchment-dim)";
    }
  }

  function driftColor(state: string): string {
    switch (state) {
      case "escalate":
        return "var(--ember, #c0392b)";
      case "warn":
        return "var(--amber, #d4a017)";
      case "insufficient":
        return "var(--parchment-dim)";
      case "ok":
        return "var(--parchment-dim)";
      default:
        return "var(--parchment-dim)";
    }
  }

  function driftLabel(state: string): string {
    switch (state) {
      case "escalate":
        return "DRIFT — escalate";
      case "warn":
        return "DRIFT — warn";
      case "insufficient":
        return "n < 8";
      case "ok":
        return "stable";
      default:
        return "—";
    }
  }

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Methods registry
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "0.75rem", fontSize: "0.9rem" }}>
        Registered extraction and analysis methods with versioned documentation.
      </p>

      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
        <Link href="/methods/candidates" className="btn" style={{ fontSize: "0.65rem", textDecoration: "none" }}>
          View candidates
        </Link>
        <a
          href={downloadHref(csvData, "text/csv")}
          download="methods.csv"
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download CSV
        </a>
        <a
          href={downloadHref(JSON.stringify(methods, null, 2), "application/json")}
          download="methods.json"
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download JSON
        </a>
      </div>

      {methods.length === 0 ? (
        <div className="portal-card" style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)" }}>
          No methods registered yet. Methods are added when extraction pipelines are configured.
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {methods.map((m) => {
            const driftActive = m.driftState === "warn" || m.driftState === "escalate";
            return (
              <li
                key={m.name}
                className="portal-card"
                style={{
                  padding: "1rem 1.25rem",
                  borderLeft: driftActive
                    ? `3px solid ${driftColor(m.driftState)}`
                    : undefined,
                  background: driftActive
                    ? "rgba(192, 57, 43, 0.04)"
                    : undefined,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
                  <Link
                    href={`/methods/${encodeURIComponent(m.name)}/${encodeURIComponent(m.latestVersion)}`}
                    style={{ color: "var(--gold)", textDecoration: "none", fontFamily: "'Cinzel', serif", fontSize: "0.85rem" }}
                  >
                    {m.name}
                  </Link>
                  <div style={{ display: "flex", gap: "0.75rem", alignItems: "baseline" }}>
                    <span
                      title={
                        m.driftLastObservedAt
                          ? `Last drift evaluation: ${m.driftLastObservedAt}`
                          : "No drift evaluation yet"
                      }
                      style={{
                        fontSize: "0.65rem",
                        color: driftColor(m.driftState),
                        textTransform: "uppercase",
                        fontWeight: driftActive ? 600 : 400,
                        letterSpacing: "0.08em",
                      }}
                    >
                      {driftLabel(m.driftState)}
                    </span>
                    <span style={{ fontSize: "0.65rem", color: statusColor(m.status), textTransform: "uppercase" }}>
                      {m.status}
                    </span>
                  </div>
                </div>
                <p style={{ marginTop: "0.35rem", color: "var(--parchment)", fontSize: "0.85rem" }}>
                  {m.description}
                </p>
                <div style={{ marginTop: "0.25rem", fontSize: "0.65rem", color: "var(--parchment-dim)" }}>
                  v{m.latestVersion} · {m.usageCount} uses
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
