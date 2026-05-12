import { Suspense, type CSSProperties } from "react";
import Link from "next/link";
import { Prisma } from "@prisma/client";
import SculptureBackdrop from "@/components/SculptureBackdrop";
import AttentionQueue from "@/components/AttentionQueue";
import AutoProcessStatusBanner from "@/components/AutoProcessStatusBanner";
import PublishToggle from "@/components/PublishToggle";
import UploadStatusBadge from "@/components/UploadStatusBadge";
import UploadRowDetail from "@/components/UploadRowDetail";
import { db } from "@/lib/db";
import { fetchDecayRecords } from "@/lib/api/round3";
import { listAttentionForFounder } from "@/lib/attention";
import { getCurrentsHealth, type CurrentsHealth } from "@/lib/currentsApi";
import { embeddingHealth, type EmbeddingHealth } from "@/lib/embeddingHealth";
import { getForecastPortfolioSurface } from "@/lib/forecastPortfolioData";
import {
  requireTenantContext,
  type TenantContext,
} from "@/lib/tenant";
import { founderDisplayName } from "@/lib/founderDisplay";
import PageHeader from "@/components/design/PageHeader";
import DashboardConclusionsClient, {
  type DashboardConclusionCard,
} from "./DashboardConclusionsClient";
import AccountDisplayNameNudge from "./AccountDisplayNameNudge";
import DashboardKeymap from "./dashboard-keymap";
import DashboardSignals, { type DashboardSignal } from "./DashboardSignals";

/**
 * Dashboard — operator home.
 *
 * The page hierarchy answers, top to bottom, the three things an
 * operator needs on landing: (1) processing health, (2) attention
 * needed, (3) recent activity. Decorative framing, the display-name
 * reminder, the shortcut hint, and the per-queue noise that earlier
 * versions stacked above the fold have all been demoted below the
 * primary work surface.
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

  const showDisplayNameNudge =
    !tenant.founderDisplayName && !tenant.accountNudgeDismissedAt;

  return (
    <div style={{ position: "relative", overflow: "hidden", minHeight: "80vh" }}>
      <DashboardKeymap />
      <SculptureBackdrop src="/sculptures/sisyphus.mesh.bin" side="right" />

      <main
        style={{
          position: "relative",
          zIndex: 1,
          maxWidth: "1100px",
          margin: "0 auto",
          padding: "1.5rem 2rem 3rem",
        }}
      >
        <PageHeader
          kicker="Operator console"
          title="Dashboard"
          description={`Welcome back, ${tenant.founderName}. Processing health, attention items, and recent activity are below.`}
          actions={
            <>
              <Link href="/knowledge?tab=library" className="btn btn--quiet">
                Library
              </Link>
              <Link href="/upload" className="btn-solid btn">
                Upload
              </Link>
            </>
          }
        />

        {/*
         * Row 1 — health pulse: currents + forecasts + embeddings, all
         * compact. Auto-process renders an inline pill when configured;
         * if it's not configured the next row shows the full setup card.
         */}
        <div
          style={{
            display: "grid",
            gap: "0.85rem",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            marginBottom: "1rem",
          }}
        >
          <Suspense fallback={null}>
            <OperatorPulse />
          </Suspense>
          <Suspense fallback={null}>
            <ForecastsPulse tenant={tenant} />
          </Suspense>
        </div>

        <AutoProcessStatusBanner />

        {/*
         * Primary work surface: the unified attention queue. Older
         * dashboards split this across per-source panels; the queue
         * collapses every founder-side queue into one ranked list so
         * "what needs your attention right now" is the first thing
         * visible above the fold.
         */}
        <Suspense fallback={null}>
          <AttentionPanel tenant={tenant} />
        </Suspense>

        {/* Compact operational signal strip — failed uploads,
         * contradictions, pending deletions, decay, unseen responses.
         * Single row of pills instead of stacked banners. */}
        <Suspense fallback={null}>
          <OperationalSignalsPanel tenant={tenant} />
        </Suspense>

        {/*
         * Recent activity grid. The two columns are the "what just
         * happened" pair: ingested uploads (left) and fresh conclusions
         * (right). Drift events sit below as the slower-moving signal.
         */}
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
                heading="Loading recent uploads…"
                hint="Recent uploads will appear once they finish processing."
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
              heading="Loading drift events…"
              hint="Drift events will appear when a conclusion's confidence shifts."
              style={{ marginTop: "0.5rem" }}
            />
          }
        >
          <DriftEventsPanel tenant={tenant} />
        </Suspense>

        {/* Low-priority reminder. Lives at the bottom so it never
         * competes with operational signals. */}
        {showDisplayNameNudge ? (
          <div style={{ marginTop: "1.5rem" }}>
            <AccountDisplayNameNudge />
          </div>
        ) : null}
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
    getCurrentsHealth({ timeoutMs: 4_000 }).catch((err) => {
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
        padding: "0.7rem 0.9rem",
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
            fontSize: "0.62rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          Currents · {healthy ? "live" : "attention"}
        </div>
        <Link href="/founder-currents" style={{ color: "var(--gold)", fontSize: "0.78rem" }}>
          Open feed
        </Link>
      </div>
      <p style={{ color: "var(--parchment)", fontSize: "0.82rem", margin: "0.4rem 0 0" }}>
        {healthy
          ? `X events: ${health?.events_last_24h}; opinions: ${health?.opinions_last_24h}; last cycle: ${health?.last_cycle_at}.`
          : problems.join("; ")}
      </p>
      {health ? (
        <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.66rem", margin: "0.35rem 0 0" }}>
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
          fontSize: "0.66rem",
          margin: "0.35rem 0 0",
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
        embeddings=
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
        padding: "0.7rem 0.9rem",
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
            fontSize: "0.62rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          Forecasts · {mode}
        </div>
        <Link href="/forecasts/portfolio" style={{ color: "var(--gold)", fontSize: "0.78rem" }}>
          Open portfolio
        </Link>
      </div>
      <p style={{ color: "var(--parchment)", fontSize: "0.82rem", margin: "0.4rem 0 0" }}>
        Paper P&L 7d: {formatDashboardUsd(pnl7d)}; open positions: {surface?.kpis.openPositions ?? 0}.
      </p>
      {surface?.mode.failedGates.length ? (
        <p className="mono" style={{ color: "var(--ember)", fontSize: "0.66rem", margin: "0.35rem 0 0" }}>
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

async function AttentionPanel({ tenant }: { tenant: TenantContext }) {
  let listing;
  try {
    listing = await listAttentionForFounder(tenant);
  } catch (err) {
    console.error("[dashboard] attention listing failed:", err);
    listing = {
      items: [],
      dismissalRates: [],
      generatedAt: new Date(),
    };
  }
  const generatedAt = listing.generatedAt;
  return (
    <AttentionQueue
      items={listing.items.map((item) => ({
        queue: item.queue,
        itemId: item.itemId,
        severity: item.severity,
        ageMs: generatedAt.getTime() - item.createdAt.getTime(),
        createdAt: item.createdAt.toISOString(),
        preview: item.preview,
        link: item.link,
      }))}
      dismissalRates={listing.dismissalRates}
      generatedAt={generatedAt.toISOString()}
    />
  );
}

type ContradictionSummary = {
  count: number;
  maxSeverity: number;
  newestAt: Date | null;
};

async function getContradictionSummary(
  tenant: TenantContext,
): Promise<ContradictionSummary> {
  try {
    const [count, newest] = await Promise.all([
      db.contradiction.count({
        where: { organizationId: tenant.organizationId, status: "active" },
      }),
      db.contradiction.findFirst({
        where: { organizationId: tenant.organizationId, status: "active" },
        orderBy: [{ severity: "desc" }, { createdAt: "desc" }],
        select: { severity: true, createdAt: true },
      }),
    ]);
    return {
      count,
      maxSeverity: newest?.severity ?? 0,
      newestAt: newest?.createdAt ?? null,
    };
  } catch {
    // Schema-lag fallback: non-status filter, severity unavailable.
    try {
      const count = await db.contradiction.count({
        where: { organizationId: tenant.organizationId },
      });
      return { count, maxSeverity: 0, newestAt: null };
    } catch {
      return { count: 0, maxSeverity: 0, newestAt: null };
    }
  }
}

async function OperationalSignalsPanel({ tenant }: { tenant: TenantContext }) {
  const visibilityScope = getUploadVisibilityScope(tenant);

  const [
    decayRecords,
    contradictions,
    pendingConclusionDeletions,
    unseenResponses,
    pendingUploadDeletions,
    uploadStatusCounts,
  ] = await Promise.all([
    fetchDecayRecords(tenant.organizationId).catch((err) => {
      console.error("[dashboard] decay query failed:", err);
      return [];
    }),
    getContradictionSummary(tenant),
    getPendingConclusionDeletionCount(tenant),
    getUnseenPublicResponseCount(tenant),
    getPendingUploadDeletionCount(tenant),
    getUploadStatusCounts(tenant, visibilityScope),
  ]);

  const decaying = decayRecords.filter((r) => r.status === "decaying").length;
  const expired = decayRecords.filter((r) => r.status === "expired").length;
  const { failed: failedUploads, processing: processingUploads } =
    uploadStatusCounts;

  const signals: DashboardSignal[] = [];

  if (failedUploads > 0) {
    signals.push({
      key: "uploads-failed",
      tone: "danger",
      label: `failed upload${failedUploads === 1 ? "" : "s"}`,
      count: failedUploads,
      href: "/knowledge?tab=library",
    });
  }
  if (processingUploads > 0) {
    signals.push({
      key: "uploads-processing",
      tone: "info",
      label: "processing",
      count: processingUploads,
      href: "/knowledge?tab=library",
    });
  }
  if (contradictions.count > 0) {
    signals.push({
      key: "contradictions",
      tone: "danger",
      label: `active contradiction${contradictions.count === 1 ? "" : "s"}`,
      count: contradictions.count,
      detail: formatContradictionDetail(contradictions),
      href: "/ops?panel=contradictions",
    });
  }
  if (expired > 0) {
    signals.push({
      key: "decay-expired",
      tone: "danger",
      label: `expired conclusion${expired === 1 ? "" : "s"}`,
      count: expired,
      href: "/ops?panel=decay",
    });
  }
  if (decaying > 0) {
    signals.push({
      key: "decay-decaying",
      tone: "warning",
      label: `decaying conclusion${decaying === 1 ? "" : "s"}`,
      count: decaying,
      href: "/ops?panel=decay",
    });
  }
  if (unseenResponses > 0) {
    signals.push({
      key: "responses-unseen",
      tone: "warning",
      label: `unseen response${unseenResponses === 1 ? "" : "s"}`,
      count: unseenResponses,
      href: "/responses",
    });
  }
  if (pendingConclusionDeletions > 0) {
    signals.push({
      key: "conclusion-deletions",
      tone: "warning",
      label: `pending conclusion deletion${pendingConclusionDeletions === 1 ? "" : "s"}`,
      count: pendingConclusionDeletions,
      href: "/knowledge?tab=conclusions",
    });
  }
  if (pendingUploadDeletions > 0) {
    signals.push({
      key: "upload-deletions",
      tone: "warning",
      label: `pending upload deletion${pendingUploadDeletions === 1 ? "" : "s"}`,
      count: pendingUploadDeletions,
      href: "/knowledge?tab=library#requests",
    });
  }

  return <DashboardSignals signals={signals} />;
}

function formatContradictionDetail(summary: ContradictionSummary): string {
  const parts: string[] = [];
  if (summary.maxSeverity > 0) {
    parts.push(`max severity ${(summary.maxSeverity * 100).toFixed(0)}%`);
  }
  if (summary.newestAt) {
    parts.push(`newest ${formatRelativeShort(summary.newestAt)}`);
  }
  return parts.join(" · ");
}

function formatRelativeShort(date: Date): string {
  const ms = Date.now() - date.getTime();
  if (ms < 60_000) return "just now";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
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

async function getUnseenPublicResponseCount(tenant: TenantContext) {
  try {
    return await db.publicResponse.count({
      where: {
        organizationId: tenant.organizationId,
        seenAt: null,
      },
    });
  } catch {
    return 0;
  }
}

async function getPendingUploadDeletionCount(tenant: TenantContext) {
  try {
    return await db.deletionRequest.count({
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
    return 0;
  }
}

async function getUploadStatusCounts(
  tenant: TenantContext,
  visibilityScope: Prisma.UploadWhereInput,
): Promise<{ failed: number; processing: number }> {
  try {
    const [processing, failed] = await Promise.all([
      db.upload.count({
        where: {
          organizationId: tenant.organizationId,
          deletedAt: null,
          status: {
            in: [
              "pending",
              "extracting",
              "awaiting_ingest",
              "processing",
              "queued_offline",
            ],
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
    return { failed, processing };
  } catch (err) {
    console.error("[dashboard] upload status queries failed (schema lag?):", err);
    return { failed: 0, processing: 0 };
  }
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
          <DashboardEmptyState
            heading="No uploads yet."
            hint="Drop a file or paste a transcript to start. Each upload is extracted, transcribed if needed, and analysed by Noosphere; the row will appear here as soon as ingestion begins."
            action={{ href: "/upload", label: "Upload" }}
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
        <DashboardEmptyState
          heading="No drift observed."
          hint="Drift events appear when a conclusion's confidence shifts after re-analysis or new evidence."
          action={{ href: "/ops?panel=decay", label: "Open decay dashboard" }}
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
  heading,
  hint,
  style,
}: {
  label: string;
  heading: string;
  hint: string;
  style?: CSSProperties;
}) {
  return (
    <section className="ascii-frame" data-label={label} style={style}>
      <DashboardEmptyState heading={heading} hint={hint} />
    </section>
  );
}

/**
 * Useful empty/loading state for `ascii-frame` sections.
 *
 * Replaces the older `LatinEmpty` (italic Latin tagline + mono
 * translation). Round 20 prefers plain English plus a clear next
 * action when the section is empty so the operator never sees a dead
 * panel.
 */
function DashboardEmptyState({
  heading,
  hint,
  action,
}: {
  heading: string;
  hint?: string;
  action?: { href: string; label: string };
}) {
  return (
    <div style={{ padding: "1rem 0.25rem", textAlign: "center" }}>
      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          fontSize: "1rem",
          color: "var(--parchment)",
          margin: 0,
        }}
      >
        {heading}
      </p>
      {hint ? (
        <p
          style={{
            fontSize: "0.82rem",
            color: "var(--parchment-dim)",
            marginTop: "0.4rem",
            maxWidth: "44ch",
            marginInline: "auto",
            lineHeight: 1.5,
          }}
        >
          {hint}
        </p>
      ) : null}
      {action ? (
        <Link
          href={action.href}
          className="btn btn--quiet"
          style={{ marginTop: "0.7rem", display: "inline-flex" }}
        >
          {action.label}
        </Link>
      ) : null}
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
