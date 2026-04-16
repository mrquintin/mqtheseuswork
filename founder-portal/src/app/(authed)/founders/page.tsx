import { Suspense } from "react";
import TemporalReplayBar from "@/components/TemporalReplayBar";
import { db } from "@/lib/db";
import { AS_OF_ISO, asOfEndUtc } from "@/lib/replayDate";
import { requireTenantContext } from "@/lib/tenant";

export default async function FoundersPage({
  searchParams,
}: {
  searchParams: Promise<{ asOf?: string }>;
}) {
  const sp = await searchParams;
  const asOf = sp.asOf;
  const end = asOf && AS_OF_ISO.test(asOf) ? asOfEndUtc(asOf) : undefined;

  const tenant = await requireTenantContext();
  if (!tenant) {
    return null;
  }

  const allFounders = await db.founder.findMany({
    where: { organizationId: tenant.organizationId },
    include: {
      uploads: {
        where: end ? { createdAt: { lte: end } } : undefined,
        select: {
          claimsCount: true,
          methodCount: true,
          substCount: true,
          principleCount: true,
          status: true,
          createdAt: true,
        },
      },
    },
    orderBy: { createdAt: "asc" },
  });

  return (
    <main style={{ maxWidth: "1000px", margin: "0 auto", padding: "3rem 2rem" }}>
      <Suspense fallback={null}>
        <TemporalReplayBar />
      </Suspense>
      {end ? (
        <p style={{ color: "var(--ember)", fontSize: "0.85rem", marginBottom: "1rem" }}>
          Replay: uploads listed per founder are those with <code>createdAt</code> ≤ end of {asOf} (UTC).
        </p>
      ) : null}
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          fontSize: "1.3rem",
          letterSpacing: "0.1em",
          color: "var(--gold)",
          marginBottom: "0.5rem",
        }}
      >
        The Founders
      </h1>
      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          fontSize: "1rem",
          color: "var(--parchment-dim)",
          marginBottom: "3rem",
        }}
      >
        Per-founder profile and upload-derived signals (portal store).
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "1rem" }}>
        {allFounders.map((f) => {
          const ingestedUploads = f.uploads.filter((u) => u.status === "ingested");
          const totalClaims = ingestedUploads.reduce((sum, u) => sum + (u.claimsCount || 0), 0);
          const totalMethod = ingestedUploads.reduce((sum, u) => sum + (u.methodCount || 0), 0);
          const totalPrinciples = ingestedUploads.reduce((sum, u) => sum + (u.principleCount || 0), 0);
          const orientation = totalClaims > 0 ? totalMethod / totalClaims : 0;

          return (
            <div key={f.id} className="portal-card">
              <h3
                style={{
                  fontFamily: "'Cinzel', serif",
                  fontSize: "1rem",
                  letterSpacing: "0.08em",
                  color: "var(--gold)",
                  marginBottom: "0.3rem",
                }}
              >
                {f.name}
              </h3>
              <p
                style={{
                  fontFamily: "'Inter', sans-serif",
                  fontSize: "0.65rem",
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  color: "var(--parchment-dim)",
                  marginBottom: "1rem",
                }}
              >
                @{f.username} · {f.role}
              </p>

              {f.bio && (
                <p
                  style={{
                    fontFamily: "'EB Garamond', serif",
                    fontSize: "0.95rem",
                    color: "var(--parchment-dim)",
                    marginBottom: "1rem",
                    fontStyle: "italic",
                  }}
                >
                  {f.bio}
                </p>
              )}

              {f.noosphereId && (
                <p style={{ fontSize: "0.65rem", color: "var(--gold-dim)", marginBottom: "0.75rem" }}>
                  Noosphere: <code>{f.noosphereId}</code>
                </p>
              )}

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(2, 1fr)",
                  gap: "0.5rem",
                  borderTop: "1px solid var(--border)",
                  paddingTop: "1rem",
                }}
              >
                <div>
                  <div style={{ fontFamily: "'Cinzel', serif", fontSize: "1.2rem", color: "var(--gold)" }}>
                    {f.uploads.length}
                  </div>
                  <div
                    style={{
                      fontFamily: "'Inter', sans-serif",
                      fontSize: "0.6rem",
                      textTransform: "uppercase",
                      letterSpacing: "0.08em",
                      color: "var(--parchment-dim)",
                    }}
                  >
                    Uploads
                  </div>
                </div>
                <div>
                  <div style={{ fontFamily: "'Cinzel', serif", fontSize: "1.2rem", color: "var(--gold)" }}>
                    {totalClaims}
                  </div>
                  <div
                    style={{
                      fontFamily: "'Inter', sans-serif",
                      fontSize: "0.6rem",
                      textTransform: "uppercase",
                      letterSpacing: "0.08em",
                      color: "var(--parchment-dim)",
                    }}
                  >
                    Claims
                  </div>
                </div>
                <div>
                  <div style={{ fontFamily: "'Cinzel', serif", fontSize: "1.2rem", color: "var(--gold)" }}>
                    {totalPrinciples}
                  </div>
                  <div
                    style={{
                      fontFamily: "'Inter', sans-serif",
                      fontSize: "0.6rem",
                      textTransform: "uppercase",
                      letterSpacing: "0.08em",
                      color: "var(--parchment-dim)",
                    }}
                  >
                    Principles
                  </div>
                </div>
                <div>
                  <div style={{ fontFamily: "'Cinzel', serif", fontSize: "1.2rem", color: "var(--gold)" }}>
                    {(orientation * 100).toFixed(0)}%
                  </div>
                  <div
                    style={{
                      fontFamily: "'Inter', sans-serif",
                      fontSize: "0.6rem",
                      textTransform: "uppercase",
                      letterSpacing: "0.08em",
                      color: "var(--parchment-dim)",
                    }}
                  >
                    Method %
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </main>
  );
}
