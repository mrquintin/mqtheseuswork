import { Suspense, type CSSProperties } from "react";
import Link from "next/link";
import { Prisma } from "@prisma/client";
import SculptureBackdrop from "@/components/SculptureBackdrop";
import AutoProcessStatusBanner from "@/components/AutoProcessStatusBanner";
import PublishToggle from "@/components/PublishToggle";
import UploadStatusBadge from "@/components/UploadStatusBadge";
import UploadRowDetail from "@/components/UploadRowDetail";
import { db } from "@/lib/db";
import { fetchDecayRecords } from "@/lib/api/round3";
import { getCurrentsHealth, type CurrentsHealth } from "@/lib/currentsApi";
import { embeddingHealth, type EmbeddingHealth } from "@/lib/embeddingHealth";
import { getForecastPortfolioSurface } from "@/lib/forecastPortfolioData";
import {
  requireTenantContext,
  type TenantContext,
} from "@/lib/tenant";
import { founderDisplayName } from "@/lib/founderDisplay";
import DashboardConclusionsClient, {
  type DashboardConclusionCard,
} from "./DashboardConclusionsClient";
import AccountDisplayNameNudge from "./AccountDisplayNameNudge";

/**
 * Dashboard — landing page after login.
 *
 * Patron sculpture: **Sisyphus**, rendered huge and dim on the right
 * side of the page. The daily act of returning to the Codex — scanning
 * newly-synthesized conclusions, picking up where yesterday's
 * deliberation left off, discovering the contradictions that drifted
 * overnight — is the boulder at firm-memory scale. The reward for a
 * round of work well done is another round of work: the dashboard is
 * the summit the figure never quite reaches, and the page is the
 * fresh slope they return to.
 */

async function getDashboardConclusions(tenant: TenantContext) {
  return db.conclusion.findMany({
    where: {
      organizationId: tenant.organizationId,
      // Hide conclusions this founder has dismissed from their
      // dashboard. Other founders' dashboards are unaffected.
      dashboardDismissals: {
        none: { founderId: tenant.founderId },
      },
    },
    orderBy: { createdAt: "desc" },
    take: 8,
  });
}

type DashboardConclusion = Awaited<
  ReturnType<typeof getDashboardConclusions>
>[number];

async function getHiddenDashboardConclusionCount(tenant: TenantContext) {
  return db.dashboardDismissal.count({
    where: {
      founderId: tenant.founderId,
      conclusion: { organizationId: tenant.organizationId },
    },
  });
}

function toDashboardConclusionCard(
  conclusion: DashboardConclusion,
): DashboardConclusionCard {
  return {
    id: conclusion.id,
    confidenceTier: conclusion.confidenceTier,
    topicHint: conclusion.topicHint,
    text: conclusion.text,
  };
}

export default async function DashboardPage() {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return null;
  }

  const [conclusions, hiddenConclusionCount] = await Promise.all([
    getDashboardConclusions(tenant),
    getHiddenDashboardConclusionCount(tenant),
  ]);

  return (
    <div style={{ position: "relative", overflow: "hidden", minHeight: "80vh" }}>
      <SculptureBackdrop src="/sculptures/sisyphus.mesh.bin" side="right" />

      <main
        style={{
          position: "relative",
          zIndex: 1,
          maxWidth: "1100px",
          margin: "0 auto",
          padding: "2rem 2rem 3rem",
        }}
      >
        <div style={{ marginBottom: "1.5rem" }}>
          <h1
            style={{
              fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
              fontSize: "2rem",
              letterSpacing: "0.18em",
              color: "var(--amber)",
              textShadow: "var(--glow-md)",
              margin: 0,
            }}
          >
            Forum
          </h1>
          <p
            className="mono"
            style={{
              fontSize: "0.62rem",
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              marginTop: "0.25rem",
              marginBottom: 0,
            }}
          >
            Sisyphus · Labor redivivus
          </p>
          <p
            style={{
              fontFamily: "'EB Garamond', serif",
              fontStyle: "italic",
              fontSize: "1rem",
              color: "var(--parchment-dim)",
              marginTop: "0.45rem",
              marginBottom: 0,
              maxWidth: "44em",
              lineHeight: 1.55,
            }}
          >
            Welcome back, {tenant.founderName}. The hearth is lit; the firm listens.
          </p>
        </div>

        {!tenant.founderDisplayName && !tenant.accountNudgeDismissedAt ? (
          <AccountDisplayNameNudge />
        ) : null}

        <AutoProcessStatusBanner />

        <div
          style={{
            display: "grid",
            gap: "1rem",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            marginBottom: "1.25rem",
          }}
        >
          <Suspense fallback={null}>
            <OperatorPulse />
          </Suspense>
          <Suspense fallback={null}>
            <ForecastsPulse tenant={tenant} />
          </Suspense>
        </div>
        <Suspense fallback={null}>
          <AttentionSignals tenant={tenant} />
        </Suspense>
        <Suspense fallback={null}>
          <UploadWorkStatus tenant={tenant} />
        </Suspense>
        <Suspense fallback={null}>
          <PendingUploadDeletionSignal tenant={tenant} />
        </Suspense>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            marginBottom: "1.25rem",
            gap: "0.75rem",
          }}
        >
          <Link href="/knowledge?tab=library" className="btn">
            Library
          </Link>
          <Link href="/upload" className="btn-solid btn">
            Upload
          </Link>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "1.5rem",
          }}
        >
          <Suspense
            fallback={
              <DashboardSectionFallback
                label="UPLOADS · ..."
                latin="Scriba praeparat."
                english="Recent uploads are loading."
              />
            }
          >
            <RecentUploadsPanel tenant={tenant} />
          </Suspense>

          <DashboardConclusionsClient
            initialConclusions={conclusions.map(toDashboardConclusionCard)}
            initialHiddenCount={hiddenConclusionCount}
          />
        </div>

        <div className="meander" aria-hidden="true" />

        <Suspense
          fallback={
            <DashboardSectionFallback
              label="DRIFT EVENTS · ..."
              latin="Fundamenta leguntur."
              english="Drift events are loading."
              style={{ marginTop: "0.5rem" }}
            />
          }
        >
          <DriftEventsPanel tenant={tenant} />
        </Suspense>
      </main>
    </div>
  );
}

function healthProblems(health: CurrentsHealth | null): string[] {
  if (!health) return ["Currents health endpoint is unreachable."];
  const problems = [...health.disabled_reasons];
  if (!health.last_cycle_at) problems.push("scheduler has not reported a cycle");
  if (health.events_last_24h === 0) problems.push("no X events recorded in the last 24h");
  if (health.opinions_last_24h === 0) problems.push("no Currents opinions generated in the last 24h");
  return problems;
}

async function OperatorPulse() {
  const [health, embeddingsHealthy] = await Promise.all([
    getCurrentsHealth().catch((err) => {
      console.error("[dashboard] currents health query failed:", err);
      return null;
    }),
    requireTenantContext()
      .then((tenant) =>
        tenant ? embeddingHealth(tenant.organizationId) : null,
      )
      .catch((err) => {
        console.error("[dashboard] embedding health query failed:", err);
        return null;
      }),
  ]);
  const problems = healthProblems(health);
  const healthy = problems.length === 0;
  const accent = healthy ? "rgba(160, 211, 170, 0.9)" : "var(--ember)";
  const embeddingAccent = embeddingHealthColor(embeddingsHealthy);

  return (
    <section
      aria-label="Currents operator pulse"
      style={{
        border: `1px solid ${accent}`,
        borderRadius: 4,
        padding: "0.85rem 1rem",
        background: healthy ? "rgba(95, 126, 93, 0.12)" : "rgba(172, 54, 37, 0.12)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "1rem",
          alignItems: "baseline",
          flexWrap: "wrap",
        }}
      >
        <div
          className="mono"
          style={{
            color: accent,
            fontSize: "0.66rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          Currents · {healthy ? "live" : "attention"}
        </div>
        <Link href="/currents" style={{ color: "var(--gold)", fontSize: "0.78rem" }}>
          Open feed
        </Link>
      </div>
      <p style={{ color: "var(--parchment)", fontSize: "0.86rem", margin: "0.55rem 0 0" }}>
        {healthy
          ? `X events: ${health?.events_last_24h}; opinions: ${health?.opinions_last_24h}; last cycle: ${health?.last_cycle_at}.`
          : problems.join("; ")}
      </p>
      {health ? (
        <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.68rem", margin: "0.45rem 0 0" }}>
          token={health.x_bearer_present ? "present" : "missing"} · curated=
          {health.curated_count} · search={health.search_count}
        </p>
      ) : null}
      <p
        className="mono"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.45rem",
          color: "var(--parchment-dim)",
          fontSize: "0.68rem",
          margin: "0.45rem 0 0",
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: embeddingAccent,
            boxShadow: `0 0 8px ${embeddingAccent}`,
            display: "inline-block",
          }}
        />
        embeddingsHealthy=
        {embeddingsHealthy
          ? `${embeddingsHealthy.embeddedCount}/${embeddingsHealthy.totalCount}`
          : "unknown"}
      </p>
    </section>
  );
}

async function ForecastsPulse({ tenant }: { tenant: TenantContext }) {
  const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  const [surface, settledLastWeek] = await Promise.all([
    getForecastPortfolioSurface(tenant.organizationId).catch((err) => {
      console.error("[dashboard] forecasts portfolio query failed:", err);
      return null;
    }),
    db.forecastBet
      .findMany({
        where: {
          organizationId: tenant.organizationId,
          mode: "PAPER",
          status: "SETTLED",
          settledAt: { gte: weekAgo },
        },
        select: { settlementPnlUsd: true },
      })
      .catch((err) => {
        console.error("[dashboard] forecasts pnl query failed:", err);
        return [];
      }),
  ]);

  const mode = surface?.mode.mode ?? "GATE-BLOCKED";
  const accent =
    mode === "PAPER"
      ? "rgba(160, 211, 170, 0.9)"
      : mode === "LIVE"
        ? "var(--amber)"
        : "var(--ember)";
  const pnl7d = settledLastWeek.reduce((sum, row) => sum + Number(row.settlementPnlUsd ?? 0), 0);

  return (
    <section
      aria-label="Forecasts portfolio pulse"
      style={{
        background: mode === "GATE-BLOCKED" ? "rgba(172, 54, 37, 0.12)" : "rgba(205, 151, 67, 0.08)",
        border: `1px solid ${accent}`,
        borderRadius: 4,
        padding: "0.85rem 1rem",
      }}
    >
      <div
        style={{
          alignItems: "baseline",
          display: "flex",
          flexWrap: "wrap",
          gap: "1rem",
          justifyContent: "space-between",
        }}
      >
        <div
          className="mono"
          style={{
            color: accent,
            fontSize: "0.66rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          Forecasts / {mode}
        </div>
        <Link href="/forecasts/portfolio" style={{ color: "var(--gold)", fontSize: "0.78rem" }}>
          Open portfolio
        </Link>
      </div>
      <p style={{ color: "var(--parchment)", fontSize: "0.86rem", margin: "0.55rem 0 0" }}>
        Paper P&L 7d: {formatDashboardUsd(pnl7d)}; open positions: {surface?.kpis.openPositions ?? 0}.
      </p>
      {surface?.mode.failedGates.length ? (
        <p className="mono" style={{ color: "var(--ember)", fontSize: "0.68rem", margin: "0.45rem 0 0" }}>
          blocked={surface.mode.failedGates.map((gate) => gate.gateName).join(", ")}
        </p>
      ) : null}
    </section>
  );
}

function formatDashboardUsd(value: number): string {
  const formatted = new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
    style: "currency",
  }).format(Math.abs(value));
  return value < 0 ? `-${formatted}` : value > 0 ? `+${formatted}` : formatted;
}

function embeddingHealthColor(health: EmbeddingHealth | null): string {
  if (!health) return "var(--ember)";
  if (health.status === "red") return "var(--ember)";
  if (health.status === "amber") return "var(--amber)";
  return "rgba(160, 211, 170, 0.9)";
}

function getUploadVisibilityScope(tenant: TenantContext): Prisma.UploadWhereInput {
  return {
    OR: [
      { visibility: { not: "private" } },
      { founderId: tenant.founderId },
    ],
  };
}

async function AttentionSignals({ tenant }: { tenant: TenantContext }) {
  const [decayRecords, activeContradictions, pendingConclusionDeletions] =
    await Promise.all([
      fetchDecayRecords(tenant.organizationId).catch((err) => {
        console.error("[dashboard] decay query failed:", err);
        return [];
      }),
      getActiveContradictionCount(tenant),
      getPendingConclusionDeletionCount(tenant),
    ]);
  const decaying = decayRecords.filter((r) => r.status === "decaying");
  const expired = decayRecords.filter((r) => r.status === "expired");

  return (
    <>
      {(expired.length > 0 || decaying.length > 0) && (
        <div
          style={{
            padding: "1rem 1.25rem",
            border: "1px solid var(--ember)",
            borderRadius: 2,
            marginBottom: "1.5rem",
          }}
        >
          <div
            style={{
              fontFamily: "'Cinzel', serif",
              fontSize: "0.65rem",
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color: "var(--ember)",
              marginBottom: "0.5rem",
            }}
          >
            Conclusions requiring attention
          </div>
          {expired.length > 0 && (
            <p style={{ fontSize: "0.85rem", color: "var(--ember)", margin: "0.25rem 0" }}>
              {expired.length} expired conclusion
              {expired.length > 1 ? "s" : ""} — confidence has decayed below
              threshold.
            </p>
          )}
          {decaying.length > 0 && (
            <p style={{ fontSize: "0.85rem", color: "var(--parchment)", margin: "0.25rem 0" }}>
              {decaying.length} decaying conclusion
              {decaying.length > 1 ? "s" : ""} — confidence is declining.
            </p>
          )}
          <Link
            href="/ops?panel=decay"
            style={{
              display: "inline-block",
              marginTop: "0.5rem",
              fontSize: "0.7rem",
              color: "var(--gold)",
              textDecoration: "none",
            }}
          >
            View decay dashboard →
          </Link>
        </div>
      )}

      {activeContradictions > 0 && (
        <Link href="/ops?panel=contradictions" style={{ textDecoration: "none", display: "block" }}>
          <div
            className="portal-card"
            style={{
              padding: "0.7rem 1rem",
              marginBottom: "1rem",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: "0.8rem",
              borderLeft: "3px solid var(--ember)",
            }}
          >
            <span style={{ color: "var(--ember)" }}>
              {activeContradictions} active contradiction
              {activeContradictions > 1 ? "s" : ""} detected
            </span>
            <span
              className="mono"
              style={{
                fontSize: "0.6rem",
                color: "var(--amber-dim)",
                textTransform: "uppercase",
              }}
            >
              Review →
            </span>
          </div>
        </Link>
      )}

      {pendingConclusionDeletions > 0 && (
        <Link href="/knowledge?tab=conclusions" style={{ textDecoration: "none", display: "block" }}>
          <div
            className="portal-card"
            style={{
              padding: "0.7rem 1rem",
              marginBottom: "1rem",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: "0.8rem",
            }}
          >
            <span style={{ color: "var(--amber)" }}>
              {pendingConclusionDeletions} pending conclusion deletion
              {pendingConclusionDeletions > 1 ? " requests" : " request"}
            </span>
            <span
              className="mono"
              style={{
                fontSize: "0.6rem",
                color: "var(--amber-dim)",
                textTransform: "uppercase",
              }}
            >
              Review →
            </span>
          </div>
        </Link>
      )}
    </>
  );
}

async function getActiveContradictionCount(tenant: TenantContext) {
  try {
    return await db.contradiction.count({
      where: {
        organizationId: tenant.organizationId,
        status: "active",
      },
    });
  } catch {
    try {
      return await db.contradiction.count({
        where: { organizationId: tenant.organizationId },
      });
    } catch {
      return 0;
    }
  }
}

async function getPendingConclusionDeletionCount(tenant: TenantContext) {
  try {
    return await db.conclusionDeletionRequest.count({
      where: {
        conclusion: { organizationId: tenant.organizationId },
        status: "pending",
      },
    });
  } catch {
    return 0;
  }
}

async function UploadWorkStatus({ tenant }: { tenant: TenantContext }) {
  const visibilityScope = getUploadVisibilityScope(tenant);
  let pendingUploads = 0;
  let failedUploads = 0;
  try {
    [pendingUploads, failedUploads] = await Promise.all([
      db.upload.count({
        where: {
          organizationId: tenant.organizationId,
          deletedAt: null,
          status: {
            in: ["pending", "extracting", "awaiting_ingest", "processing", "queued_offline"],
          },
          ...visibilityScope,
        },
      }),
      db.upload.count({
        where: {
          organizationId: tenant.organizationId,
          deletedAt: null,
          status: "failed",
          ...visibilityScope,
        },
      }),
    ]);
  } catch (err) {
    console.error("[dashboard] upload status queries failed (schema lag?):", err);
  }

  if (failedUploads === 0 && pendingUploads === 0) return null;

  return (
    <Link href="/knowledge?tab=library" style={{ textDecoration: "none", display: "block" }}>
      <div
        className="portal-card"
        style={{
          padding: "0.7rem 1rem",
          marginBottom: "1rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: "0.8rem",
        }}
      >
        <span style={{ color: "var(--parchment-dim)" }}>
          {failedUploads > 0 && (
            <span style={{ color: "var(--ember)" }}>
              {failedUploads} failed upload{failedUploads > 1 ? "s" : ""}
            </span>
          )}
          {failedUploads > 0 && pendingUploads > 0 && " · "}
          {pendingUploads > 0 && <span>{pendingUploads} processing</span>}
        </span>
        <span
          className="mono"
          style={{
            fontSize: "0.6rem",
            color: "var(--amber-dim)",
            textTransform: "uppercase",
          }}
        >
          View in library →
        </span>
      </div>
    </Link>
  );
}

async function PendingUploadDeletionSignal({ tenant }: { tenant: TenantContext }) {
  let pendingRequestCount = 0;
  try {
    pendingRequestCount = await db.deletionRequest.count({
      where: {
        status: "pending",
        upload: {
          organizationId: tenant.organizationId,
          founderId: tenant.founderId,
          deletedAt: null,
        },
      },
    });
  } catch (err) {
    console.error("[dashboard] upload deletion request query failed:", err);
  }

  if (pendingRequestCount === 0) return null;

  return (
    <Link
      href="/knowledge?tab=library#requests"
      style={{ textDecoration: "none", display: "block" }}
    >
      <div
        className="portal-card"
        style={{
          border: "1px solid var(--amber)",
          background:
            "linear-gradient(180deg, rgba(212,160,23,0.10), rgba(212,160,23,0.03))",
          padding: "0.9rem 1.1rem",
          marginBottom: "1.5rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "1rem",
          transition: "border-color 0.2s ease",
        }}
      >
        <span
          className="mono"
          style={{
            color: "var(--amber)",
            fontSize: "0.62rem",
            letterSpacing: "0.28em",
            textTransform: "uppercase",
          }}
        >
          ⚠ {pendingRequestCount} deletion request
          {pendingRequestCount === 1 ? "" : "s"} awaiting your decision
        </span>
        <span
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.6rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
          }}
        >
          Review →
        </span>
      </div>
    </Link>
  );
}

async function RecentUploadsPanel({ tenant }: { tenant: TenantContext }) {
  const recentUploadsArgs = {
    where: {
      organizationId: tenant.organizationId,
      deletedAt: null,
      ...getUploadVisibilityScope(tenant),
    },
    orderBy: { createdAt: "desc" },
    take: 12,
    select: {
      id: true,
      title: true,
      status: true,
      errorMessage: true,
      extractionMethod: true,
      visibility: true,
      publishedAt: true,
      slug: true,
      createdAt: true,
      founder: { select: { displayName: true, name: true, username: true } },
    },
  } satisfies Prisma.UploadFindManyArgs;
  let recentUploads: Prisma.UploadGetPayload<typeof recentUploadsArgs>[] = [];
  try {
    recentUploads = await db.upload.findMany(recentUploadsArgs);
  } catch (err) {
    console.error("[dashboard] recent upload query failed (schema lag?):", err);
  }

  return (
    <section
      className="ascii-frame"
      data-label={`UPLOADS · ${toRoman(recentUploads.length) || "0"}`}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {recentUploads.length === 0 ? (
          <LatinEmpty
            latin="Scriba exspectat."
            english="The scribe awaits — nothing ingested yet."
          />
        ) : (
          recentUploads.map((u) => (
            <div key={u.id} className="portal-card" style={{ padding: "0.9rem 1rem" }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "1rem",
                  alignItems: "flex-start",
                }}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.45rem",
                      overflow: "hidden",
                      flexWrap: "wrap",
                    }}
                  >
                    <Link
                      href={`/upload/${u.id}`}
                      style={{
                        fontFamily: "'EB Garamond', serif",
                        color: "var(--parchment)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        textDecoration: "none",
                        whiteSpace: "nowrap",
                        minWidth: 0,
                      }}
                    >
                      {u.title}
                    </Link>
                    <UploadStatusBadge status={u.status} />
                    {u.visibility === "private" ? (
                      <span
                        className="mono"
                        title="Private — only you see this row. Noosphere still analyses it."
                        style={{
                          fontSize: "0.5rem",
                          letterSpacing: "0.22em",
                          textTransform: "uppercase",
                          color: "var(--amber)",
                          border: "1px solid var(--amber-dim)",
                          padding: "0.08rem 0.38rem",
                          borderRadius: "2px",
                          flexShrink: 0,
                        }}
                      >
                        Private
                      </span>
                    ) : u.visibility === "semi-private" ? (
                      <span
                        className="mono"
                        title="Semi-private — firm sees this; public blog never does. Noosphere still analyses it."
                        style={{
                          fontSize: "0.5rem",
                          letterSpacing: "0.22em",
                          textTransform: "uppercase",
                          color: "var(--amber)",
                          border: "1px solid var(--amber-dim)",
                          padding: "0.08rem 0.38rem",
                          borderRadius: "2px",
                          flexShrink: 0,
                        }}
                      >
                        Semi-private
                      </span>
                    ) : null}
                  </div>
                  <div
                    className="mono"
                    style={{
                      fontSize: "0.65rem",
                      color: "var(--parchment-dim)",
                      marginTop: "0.25rem",
                    }}
                  >
                    {founderDisplayName(u.founder)} · {new Date(u.createdAt).toLocaleDateString()}
                  </div>
                  <UploadRowDetail upload={u} />
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: "0.5rem",
                    alignItems: "center",
                    flexShrink: 0,
                    flexWrap: "wrap",
                    justifyContent: "flex-end",
                  }}
                >
                  {u.status === "ingested" ? (
                    <PublishToggle
                      uploadId={u.id}
                      initialPublishedAt={u.publishedAt}
                      initialSlug={u.slug}
                    />
                  ) : null}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

async function DriftEventsPanel({ tenant }: { tenant: TenantContext }) {
  const drifts = await db.driftEvent.findMany({
    where: { organizationId: tenant.organizationId },
    orderBy: { observedAt: "desc" },
    take: 6,
  });

  return (
    <section
      className="ascii-frame"
      data-label={`DRIFT EVENTS · ${toRoman(drifts.length) || "0"}`}
      style={{ marginTop: "0.5rem" }}
    >
      {drifts.length === 0 ? (
        <LatinEmpty
          latin="Fundamenta firma."
          english="No drift observed — the foundations are firm."
        />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {drifts.map((d) => (
            <div key={d.id} className="portal-card" style={{ padding: "0.9rem 1rem" }}>
              <div className="mono" style={{ fontSize: "0.72rem", color: "var(--ember)" }}>
                score {(d.driftScore * 100).toFixed(0)}% · {d.targetKind}{" "}
                {d.targetId.slice(0, 8)}…
              </div>
              <p
                style={{
                  marginTop: "0.35rem",
                  fontSize: "0.9rem",
                  color: "var(--parchment-dim)",
                  lineHeight: 1.5,
                }}
              >
                {d.naturalLanguageSummary || d.notes || "—"}
              </p>
              <div
                className="mono"
                style={{
                  fontSize: "0.6rem",
                  color: "var(--parchment-dim)",
                  marginTop: "0.3rem",
                }}
              >
                {new Date(d.observedAt).toLocaleDateString()}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function DashboardSectionFallback({
  label,
  latin,
  english,
  style,
}: {
  label: string;
  latin: string;
  english: string;
  style?: CSSProperties;
}) {
  return (
    <section className="ascii-frame" data-label={label} style={style}>
      <LatinEmpty latin={latin} english={english} />
    </section>
  );
}

/** Inline Latin empty state for populated `ascii-frame` sections. */
function LatinEmpty({ latin, english }: { latin: string; english: string }) {
  return (
    <div style={{ padding: "1rem 0.25rem", textAlign: "center" }}>
      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          fontStyle: "italic",
          fontSize: "1rem",
          color: "var(--parchment)",
          margin: 0,
        }}
      >
        {latin}
      </p>
      <p
        className="mono"
        style={{
          fontSize: "0.7rem",
          color: "var(--parchment-dim)",
          marginTop: "0.25rem",
        }}
      >
        {english}
      </p>
    </div>
  );
}

/** Small positive int → Roman numerals, for display accents only. */
function toRoman(n: number): string {
  if (!n || n < 1) return "";
  const table: [number, string][] = [
    [10, "X"],
    [9, "IX"],
    [5, "V"],
    [4, "IV"],
    [1, "I"],
  ];
  let out = "";
  let rem = n;
  for (const [v, s] of table) {
    while (rem >= v) {
      out += s;
      rem -= v;
    }
  }
  return out;
}
