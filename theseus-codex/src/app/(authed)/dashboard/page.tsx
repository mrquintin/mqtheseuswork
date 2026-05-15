import fs from "node:fs";
import path from "node:path";
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
import PageHeader from "@/components/design/PageHeader";
import PrimaryNav, { PrimaryNavLink } from "@/components/nav/PrimaryNav";
import DashboardConclusionsClient, {
  type DashboardConclusionCard,
} from "./DashboardConclusionsClient";
import AccountDisplayNameNudge from "./AccountDisplayNameNudge";
import DashboardSignals, { type DashboardSignal } from "./DashboardSignals";
import { listAcceptedPrinciples } from "@/lib/principlesApi";

/**
 * Dashboard — operator home.
 *
 * Round 21 makes principles the spine: the main rail is "Active
 * principles" — the firm's accepted principles, conviction-ranked, so
 * the operator lands on the rules the firm is currently using to
 * judge new evidence. The previous main rail ("Recent conclusions")
 * shrinks to a secondary panel beneath it, because conclusions are
 * now evidence for or against a principle rather than the top-level
 * artifact.
 *
 * Hierarchy, top to bottom: (1) processing health, (2) compact review
 * signals, (3) Active principles rail (primary), (4) Recent
 * conclusions and uploads (secondary), (5) drift events and reviewer-
 * agreement telemetry. Decorative framing and the display-name
 * reminder stay demoted below the primary work surface.
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
          description={`Welcome back, ${tenant.founderName}. Processing health, review signals, and recent activity are below.`}
          actions={
            <PrimaryNav>
              <PrimaryNavLink href="/principles">Principles</PrimaryNavLink>
              <PrimaryNavLink href="/knowledge?tab=library">
                Library
              </PrimaryNavLink>
              <PrimaryNavLink href="/upload" emphasis="solid">
                Upload
              </PrimaryNavLink>
            </PrimaryNav>
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
         * The dashboard review queue ("Attention") used to live here.
         * Removed in Round 20: the founder reported the word and the
         * panel did not communicate, and the same surface is reachable
         * from `/attention` via the operational signals strip below.
         * See docs/operator/dashboard_terminology.md.
         */}

        {/* Compact operational signal strip — failed uploads,
         * contradictions, pending deletions, decay, unseen responses.
         * Single row of pills instead of stacked banners. */}
        <Suspense fallback={null}>
          <OperationalSignalsPanel tenant={tenant} />
        </Suspense>

        {/*
         * Primary rail — Active principles. The firm's spine: the
         * rules it is currently using to judge new evidence,
         * conviction-ranked with the most recently informed by a new
         * decision floated to the top. Conclusions are demoted to the
         * secondary grid below since they are now evidence for or
         * against a principle.
         */}
        <Suspense
          fallback={
            <DashboardSectionFallback
              label="ACTIVE PRINCIPLES · ..."
              heading="Loading active principles…"
              hint="Accepted principles appear here, conviction-ranked."
              style={{ marginTop: "1rem" }}
            />
          }
        >
          <ActivePrinciplesPanel tenant={tenant} />
        </Suspense>

        {/*
         * Secondary grid — what just happened. Ingested uploads
         * (left) and fresh conclusions (right). These used to be the
         * dashboard's main rail; in Round 21 they sit one tier below
         * Active principles.
         */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "1.5rem",
            marginTop: "1.25rem",
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

        {/* Reviewer-agreement model: is the pre-review contention
         * predictor earning its keep, or just adding noise? Tracks the
         * model's held-out calibration over time. */}
        <Suspense fallback={null}>
          <ReviewerAgreementTrendsPanel />
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

/**
 * Active principles rail — the dashboard's primary surface in Round 21.
 *
 * Lists the firm's accepted principles, ranked by:
 *   1. recent decision relevance — when the principle's underlying
 *      cluster includes a conclusion that drifted, was created, or
 *      was updated in the last 14 days, the row floats to the top so
 *      the operator sees what the firm is currently consulting;
 *   2. conviction score (descending) for the remainder.
 *
 * The panel is conviction-honest: the score is rendered next to each
 * row, the same way the public /principles index renders it. Domains
 * and cluster size are shown so the operator can tell at a glance
 * whether the principle is broad or narrow.
 */
async function ActivePrinciplesPanel({ tenant }: { tenant: TenantContext }) {
  const principles = await listAcceptedPrinciples(tenant.organizationId).catch(
    (err) => {
      console.error("[dashboard] active principles query failed:", err);
      return [];
    },
  );
  if (principles.length === 0) {
    return (
      <section
        className="ascii-frame"
        data-label="ACTIVE PRINCIPLES · 0"
        style={{ marginTop: "1rem" }}
      >
        <DashboardEmptyState
          heading="No accepted principles yet."
          hint="Principles surface here once a distilled candidate has been accepted in the triage queue."
          action={{ href: "/principles/queue", label: "Open triage queue" }}
        />
      </section>
    );
  }

  // Decision-relevance bump: principles whose cluster includes a
  // conclusion changed in the last 14 days are sorted to the front.
  const allClusterIds = Array.from(
    new Set(principles.flatMap((p) => p.clusterConclusionIds)),
  );
  const recentWindow = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000);
  let recentConclusionIds = new Set<string>();
  if (allClusterIds.length > 0) {
    try {
      const recent = await db.conclusion.findMany({
        where: {
          id: { in: allClusterIds },
          organizationId: tenant.organizationId,
          OR: [{ createdAt: { gte: recentWindow } }, { updatedAt: { gte: recentWindow } }],
        },
        select: { id: true },
      });
      recentConclusionIds = new Set(recent.map((r) => r.id));
    } catch (err) {
      console.error("[dashboard] recent conclusion lookup failed:", err);
    }
  }

  const ranked = [...principles].sort((a, b) => {
    const aHot = a.clusterConclusionIds.some((id) => recentConclusionIds.has(id))
      ? 1
      : 0;
    const bHot = b.clusterConclusionIds.some((id) => recentConclusionIds.has(id))
      ? 1
      : 0;
    if (aHot !== bHot) return bHot - aHot;
    return b.convictionScore - a.convictionScore;
  });
  const visible = ranked.slice(0, 8);

  return (
    <section
      className="ascii-frame"
      data-label={`ACTIVE PRINCIPLES · ${toRoman(visible.length) || visible.length}`}
      data-testid="dashboard-active-principles"
      style={{ marginTop: "1rem" }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {visible.map((p) => {
          const hot = p.clusterConclusionIds.some((id) =>
            recentConclusionIds.has(id),
          );
          return (
            <div
              key={p.id}
              className="portal-card"
              style={{
                padding: "0.85rem 1rem",
                borderLeft: hot ? "3px solid var(--gold)" : undefined,
              }}
            >
              <div
                style={{
                  alignItems: "baseline",
                  display: "flex",
                  gap: "1rem",
                  justifyContent: "space-between",
                }}
              >
                <Link
                  href={`/principles/${p.id}`}
                  style={{
                    color: "var(--parchment)",
                    fontFamily: "'EB Garamond', serif",
                    fontSize: "1rem",
                    textDecoration: "none",
                  }}
                >
                  {p.text}
                </Link>
                <span
                  className="mono"
                  title="Conviction (cross-domain convergence)"
                  style={{
                    color: "var(--amber)",
                    fontSize: "0.68rem",
                    letterSpacing: "0.18em",
                  }}
                >
                  {p.convictionScore.toFixed(2)}
                </span>
              </div>
              <div
                className="mono"
                style={{
                  color: "var(--parchment-dim)",
                  display: "flex",
                  flexWrap: "wrap",
                  fontSize: "0.58rem",
                  gap: "0.6rem",
                  letterSpacing: "0.18em",
                  marginTop: "0.35rem",
                  textTransform: "uppercase",
                }}
              >
                <span>cluster · {p.clusterConclusionIds.length}</span>
                <span>domains · {p.domainBreadth}</span>
                {hot ? (
                  <span style={{ color: "var(--gold)" }}>
                    recently informed
                  </span>
                ) : null}
                {p.publicVisible ? (
                  <span style={{ color: "var(--gold)" }}>public</span>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: "0.6rem" }}>
        <Link
          href="/principles"
          className="mono"
          style={{
            color: "var(--gold)",
            fontSize: "0.62rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            textDecoration: "none",
          }}
        >
          Open principles index →
        </Link>
      </div>
    </section>
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

type AgreementCalibrationSnapshot = {
  observed_at: string;
  skill: number;
  mae: number;
  pearson_r: number;
  n_eval: number;
};

type AgreementModelArtifact = {
  model: { trained_at: string; n_train: number };
  evaluation: {
    skill: number;
    mae: number;
    baseline_mae: number;
    pearson_r: number;
    beats_baseline: boolean;
    n_eval: number;
  };
  calibration_history: AgreementCalibrationSnapshot[];
  routing_ablation?: {
    cost_saving_vs_expanded_usd: number;
    coverage_delta_vs_expanded: number;
    expand_count: number;
    keep_count: number;
    shrink_count: number;
  };
};

/**
 * Read the reviewer-agreement model artifact written by
 * `train_agreement_model.sh`. Missing file → null (the widget renders an
 * empty state rather than erroring).
 */
function readAgreementModelArtifact(): AgreementModelArtifact | null {
  const candidates = [
    path.join(
      process.cwd(),
      "..",
      "noosphere_data",
      "agreement_model",
      "model.json",
    ),
    path.join(process.cwd(), "public", "agreement_model", "model.json"),
  ];
  for (const p of candidates) {
    try {
      return JSON.parse(fs.readFileSync(p, "utf8")) as AgreementModelArtifact;
    } catch {
      // try next
    }
  }
  return null;
}

/** Median helper for the trailing-baseline drift check. */
function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * Reviewer-agreement trends — does the pre-review contention predictor
 * actually predict agreement, or is it just adding noise?
 *
 * The honest framing is the point: ``skill`` is reported relative to the
 * predict-the-mean baseline, and the widget says "no skill" plainly when
 * the model is not earning its keep. Calibration is tracked over every
 * training run so a slip shows up here before it costs the firm a bad
 * routing call.
 */
async function ReviewerAgreementTrendsPanel() {
  const artifact = readAgreementModelArtifact();

  if (!artifact || artifact.calibration_history.length === 0) {
    return (
      <section
        className="ascii-frame"
        data-label="REVIEWER AGREEMENT · —"
        style={{ marginTop: "0.5rem" }}
      >
        <DashboardEmptyState
          heading="No reviewer-agreement model yet."
          hint="Run noosphere/scripts/train_agreement_model.sh to fit the pre-review contention predictor. Its held-out calibration will be tracked here."
        />
      </section>
    );
  }

  const evalReport = artifact.evaluation;
  const history = artifact.calibration_history;
  const latest = history[history.length - 1];
  const skillPct = Math.round(evalReport.skill * 100);
  const beats = evalReport.beats_baseline;

  // Trailing-baseline calibration check: has the latest run's skill
  // slipped well below the median of prior runs? Mirrors the spirit of
  // the method-drift detector's trailing baseline, kept lightweight for
  // a dashboard glance.
  const priorSkills = history.slice(0, -1).map((s) => s.skill);
  const hasBaseline = priorSkills.length >= 2;
  const baselineSkill = hasBaseline ? median(priorSkills) : null;
  const drifting =
    baselineSkill !== null && latest.skill < baselineSkill - 0.15;

  const accent = !beats
    ? "var(--ember)"
    : drifting
      ? "var(--amber)"
      : "rgba(160, 211, 170, 0.9)";
  const verdict = !beats
    ? "No skill — the model is not beating the predict-the-mean baseline. Treat its predictions as noise until retrained."
    : drifting
      ? "Calibration slipping — held-out skill has dropped below its trailing baseline. The model is drifting; retrain and review."
      : "Calibration holding — the model predicts inter-reviewer agreement with real skill over the held-out tournament shard.";

  const maxAbsSkill = Math.max(
    0.05,
    ...history.map((s) => Math.abs(s.skill)),
  );

  return (
    <section
      className="ascii-frame"
      data-label={`REVIEWER AGREEMENT · ${skillPct}%`}
      style={{ marginTop: "0.5rem" }}
    >
      <div
        className="portal-card"
        style={{
          padding: "0.9rem 1rem",
          borderLeft: `3px solid ${accent}`,
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
              letterSpacing: "0.16em",
              textTransform: "uppercase",
            }}
          >
            Reviewer-agreement model ·{" "}
            {!beats ? "no skill" : drifting ? "drift watch" : "healthy"}
          </div>
          <Link
            href="/methodology/redteam"
            style={{ color: "var(--gold)", fontSize: "0.74rem" }}
          >
            Red-team tournament
          </Link>
        </div>

        <p
          style={{
            color: "var(--parchment)",
            fontSize: "0.84rem",
            margin: "0.45rem 0 0",
            lineHeight: 1.5,
          }}
        >
          {verdict}
        </p>

        {/* Headline numbers — skill is always reported next to the
         * baseline it is measured against. */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
            gap: "0.4rem",
            marginTop: "0.6rem",
          }}
        >
          <AgreementStat
            label="Held-out skill"
            value={`${evalReport.skill >= 0 ? "+" : ""}${skillPct}%`}
            accent={accent}
          />
          <AgreementStat
            label="Pearson r"
            value={`${evalReport.pearson_r >= 0 ? "+" : ""}${evalReport.pearson_r.toFixed(2)}`}
          />
          <AgreementStat
            label="MAE vs baseline"
            value={`${evalReport.mae.toFixed(3)} / ${evalReport.baseline_mae.toFixed(3)}`}
          />
          <AgreementStat
            label="Holdout / train n"
            value={`${evalReport.n_eval} / ${artifact.model.n_train}`}
          />
        </div>

        {/* Skill over time — one bar per training run. Above the zero
         * line = beats baseline, below = noise. */}
        <div style={{ marginTop: "0.7rem" }}>
          <div
            className="mono"
            style={{
              fontSize: "0.56rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
              marginBottom: "0.3rem",
            }}
          >
            Held-out skill over {history.length} training run
            {history.length === 1 ? "" : "s"}
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "stretch",
              gap: "2px",
              height: "44px",
            }}
          >
            {history.slice(-24).map((snap, i) => {
              const frac = Math.min(1, Math.abs(snap.skill) / maxAbsSkill);
              const positive = snap.skill >= 0;
              return (
                <div
                  key={`${snap.observed_at}-${i}`}
                  title={`${snap.observed_at.slice(0, 16)} · skill ${(snap.skill * 100).toFixed(0)}% · r ${snap.pearson_r.toFixed(2)} · n ${snap.n_eval}`}
                  style={{
                    flex: 1,
                    minWidth: "3px",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "center",
                  }}
                >
                  <div style={{ flex: 1, display: "flex", alignItems: "flex-end" }}>
                    <div
                      style={{
                        width: "100%",
                        height: positive ? `${frac * 100}%` : "0%",
                        background: "rgba(160, 211, 170, 0.8)",
                      }}
                    />
                  </div>
                  <div style={{ height: "1px", background: "var(--parchment-dim)" }} />
                  <div style={{ flex: 1, display: "flex", alignItems: "flex-start" }}>
                    <div
                      style={{
                        width: "100%",
                        height: positive ? "0%" : `${frac * 100}%`,
                        background: "var(--ember)",
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {artifact.routing_ablation ? (
          <p
            className="mono"
            style={{
              fontSize: "0.64rem",
              color: "var(--parchment-dim)",
              margin: "0.6rem 0 0",
              lineHeight: 1.5,
            }}
          >
            routing ablation: {artifact.routing_ablation.expand_count} expanded ·{" "}
            {artifact.routing_ablation.keep_count} kept ·{" "}
            {artifact.routing_ablation.shrink_count} shrunk · saved $
            {artifact.routing_ablation.cost_saving_vs_expanded_usd.toFixed(4)} vs
            always-expanded, at {artifact.routing_ablation.coverage_delta_vs_expanded}{" "}
            reviewer-coverage
          </p>
        ) : null}

        <div
          className="mono"
          style={{
            fontSize: "0.6rem",
            color: "var(--parchment-dim)",
            marginTop: "0.4rem",
          }}
        >
          last trained {latest.observed_at.slice(0, 16)}
        </div>
      </div>
    </section>
  );
}

function AgreementStat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div
      style={{
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: "2px",
        padding: "0.4rem 0.55rem",
      }}
    >
      <div
        className="mono"
        style={{
          fontSize: "0.54rem",
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          color: "var(--parchment-dim)",
        }}
      >
        {label}
      </div>
      <div
        style={{
          color: accent ?? "var(--parchment)",
          fontSize: "0.82rem",
          marginTop: "0.15rem",
        }}
      >
        {value}
      </div>
    </div>
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
