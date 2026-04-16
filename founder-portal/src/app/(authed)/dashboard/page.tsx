import Link from "next/link";
import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

export default async function DashboardPage() {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return null;
  }

  const uploads = await db.upload.findMany({
    where: { organizationId: tenant.organizationId },
    orderBy: { createdAt: "desc" },
    take: 12,
    include: { founder: { select: { name: true } } },
  });

  const conclusions = await db.conclusion.findMany({
    where: { organizationId: tenant.organizationId },
    orderBy: { createdAt: "desc" },
    take: 8,
  });

  const drifts = await db.driftEvent.findMany({
    where: { organizationId: tenant.organizationId },
    orderBy: { observedAt: "desc" },
    take: 6,
  });

  const statusBadge = (status: string) => {
    const cls: Record<string, string> = {
      pending: "badge-pending",
      processing: "badge-processing",
      ingested: "badge-ingested",
      failed: "badge-failed",
    };
    return `badge ${cls[status] || "badge-pending"}`;
  };

  return (
    <main style={{ maxWidth: "1000px", margin: "0 auto", padding: "3rem 2rem" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "2rem",
        }}
      >
        <div>
          <h1
            style={{
              fontFamily: "'Cinzel', serif",
              fontSize: "1.5rem",
              letterSpacing: "0.1em",
              color: "var(--gold)",
            }}
          >
            At a glance
          </h1>
          <p
            style={{
              fontFamily: "'Inter', sans-serif",
              fontSize: "0.7rem",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
            }}
          >
            Recent activity across the portal store
          </p>
        </div>
        <Link href="/upload" className="btn-solid btn">
          Upload
        </Link>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2rem" }}>
        <section>
          <h2
            style={{
              fontFamily: "'Cinzel', serif",
              fontSize: "0.85rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
              marginBottom: "1rem",
            }}
          >
            Recent uploads
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {uploads.length === 0 ? (
              <p style={{ color: "var(--parchment-dim)" }}>No uploads yet.</p>
            ) : (
              uploads.map((u) => (
                <div key={u.id} className="portal-card" style={{ padding: "1rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}>
                    <div>
                      <div style={{ fontFamily: "'EB Garamond', serif", color: "var(--parchment)" }}>
                        {u.title}
                      </div>
                      <div style={{ fontSize: "0.7rem", color: "var(--parchment-dim)", marginTop: "0.25rem" }}>
                        {u.founder.name} · {new Date(u.createdAt).toLocaleString()}
                      </div>
                    </div>
                    <span className={statusBadge(u.status)}>{u.status}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        <section>
          <h2
            style={{
              fontFamily: "'Cinzel', serif",
              fontSize: "0.85rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
              marginBottom: "1rem",
            }}
          >
            New conclusions
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {conclusions.map((c) => (
              <div key={c.id} className="portal-card" style={{ padding: "1rem" }}>
                <div style={{ fontSize: "0.65rem", color: "var(--gold-dim)", textTransform: "uppercase" }}>
                  {c.confidenceTier} · {c.topicHint || "general"}
                </div>
                <p style={{ marginTop: "0.35rem", fontSize: "0.9rem", color: "var(--parchment)" }}>{c.text}</p>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section style={{ marginTop: "2.5rem" }}>
        <h2
          style={{
            fontFamily: "'Cinzel', serif",
            fontSize: "0.85rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "var(--parchment-dim)",
            marginBottom: "1rem",
          }}
        >
          Recent drift events
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {drifts.map((d) => (
            <div key={d.id} className="portal-card" style={{ padding: "1rem" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--ember)" }}>
                score {(d.driftScore * 100).toFixed(0)}% · {d.targetKind} {d.targetId.slice(0, 8)}…
              </div>
              <p style={{ marginTop: "0.35rem", fontSize: "0.85rem", color: "var(--parchment-dim)" }}>
                {d.naturalLanguageSummary || d.notes || "—"}
              </p>
              <div style={{ fontSize: "0.65rem", color: "var(--parchment-dim)", marginTop: "0.25rem" }}>
                {new Date(d.observedAt).toLocaleDateString()}
              </div>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
