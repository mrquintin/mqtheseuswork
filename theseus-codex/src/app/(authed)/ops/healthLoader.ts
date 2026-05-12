/**
 * Server-only loader for the /ops triage console.
 *
 * Aggregates the existing health signals scattered across the codebase
 * into one structure so the page can render a triage-first view (broken
 * now → running → recent successes → diagnostics). Every fetch is
 * settled, never thrown — a failing branch becomes a `null` field, not
 * a 500 on the whole console.
 */

import { db } from "@/lib/db";
import type { TenantContext } from "@/lib/tenant";
import {
  getCurrentsHealth,
  type CurrentsHealth,
} from "@/lib/currentsApi";
import {
  embeddingHealth,
  type EmbeddingHealth,
} from "@/lib/embeddingHealth";
import {
  listInFlightTraces,
  listRecentTraces,
  listRecentAlerts,
  type AlertEventRow,
  type TraceSummary,
} from "@/lib/opsApi";
import {
  UPLOAD_STATUSES,
  type UploadStatus,
} from "@/lib/uploadStatus";

export type UploadStatusBuckets = Record<UploadStatus, number>;

export type StaleUpload = {
  id: string;
  title: string;
  status: UploadStatus;
  updatedAt: Date;
  minutesStuck: number;
};

export type FailedUpload = {
  id: string;
  title: string;
  errorMessage: string | null;
  updatedAt: Date;
};

export type AutoProcessingEnv = {
  githubDispatchToken: boolean;
  openaiKey: boolean;
  anthropicKey: boolean;
  xBearerToken: boolean | null;
  githubDispatchRepo: string;
  workflowUrl: string;
};

export type WorkflowReference = {
  name: string;
  file: string;
  url: string;
  cadence: string;
  purpose: string;
};

export type CurrentsBackend = {
  reachable: boolean;
  error: string | null;
  health: CurrentsHealth | null;
  url: string;
};

/**
 * The threshold the GitHub Actions sweep uses (`stale_before = 90 min`)
 * for retrying transient statuses. Mirrored here so the founder sees
 * the same definition of "stuck" the recovery job uses.
 */
const STALE_MINUTES = 90;

const TRANSIENT_STATUSES: ReadonlySet<UploadStatus> = new Set<UploadStatus>([
  "extracting",
  "awaiting_ingest",
  "processing",
]);

export type OpsHealth = {
  generatedAt: Date;
  uploads: {
    buckets: UploadStatusBuckets;
    inFlight: number;
    queued: number;
    failed24h: number;
    lastIngestedAt: Date | null;
    lastFailureAt: Date | null;
    staleInProgress: StaleUpload[];
    recentFailures: FailedUpload[];
  };
  traces: {
    inFlight: TraceSummary[];
    recent: TraceSummary[];
    lastError: TraceSummary | null;
    lastSuccess: TraceSummary | null;
  };
  alerts: {
    unacknowledged: AlertEventRow[];
    recent: AlertEventRow[];
  };
  embedding: EmbeddingHealth | null;
  currents: CurrentsBackend;
  autoProcessing: AutoProcessingEnv;
  workflows: WorkflowReference[];
  /**
   * True only when the long-running scheduler container (`Dockerfile.scheduler`
   * → `python -m noosphere.currents loop`) is provably reachable via the
   * Currents backend. False/unknown means Currents and Articles depend on
   * the every-10-minute GitHub Actions cron, which is the fallback path
   * and is not guaranteed to run if `CODEX_DATABASE_URL` is missing.
   */
  schedulerProvisioned: boolean | "unknown";
};

function emptyBuckets(): UploadStatusBuckets {
  const empty = Object.fromEntries(
    UPLOAD_STATUSES.map((s) => [s, 0]),
  ) as UploadStatusBuckets;
  return empty;
}

async function loadUploadHealth(organizationId: string) {
  const buckets = emptyBuckets();
  let inFlight = 0;
  let queued = 0;
  let failed24h = 0;
  let lastIngestedAt: Date | null = null;
  let lastFailureAt: Date | null = null;
  let staleInProgress: StaleUpload[] = [];
  let recentFailures: FailedUpload[] = [];

  const since = new Date(Date.now() - 24 * 3600 * 1000);

  try {
    const grouped = await db.upload.groupBy({
      by: ["status"],
      where: { organizationId, deletedAt: null },
      _count: { _all: true },
    });
    for (const row of grouped) {
      const status = row.status as string;
      // queued_offline is legacy → fold into pending; anything else
      // unknown is also folded into pending so the totals reconcile.
      const bucket: UploadStatus =
        (UPLOAD_STATUSES as readonly string[]).includes(status)
          ? (status as UploadStatus)
          : "pending";
      buckets[bucket] += row._count._all;
    }
    inFlight =
      buckets.extracting + buckets.awaiting_ingest + buckets.processing;
    queued = buckets.pending;
  } catch (err) {
    console.error("ops_health_upload_groupby_failed", err);
  }

  try {
    const failed = await db.upload.findMany({
      where: {
        organizationId,
        deletedAt: null,
        status: "failed",
        updatedAt: { gte: since },
      },
      select: { id: true, title: true, errorMessage: true, updatedAt: true },
      orderBy: { updatedAt: "desc" },
      take: 10,
    });
    failed24h = failed.length;
    recentFailures = failed.map((u) => ({
      id: u.id,
      title: u.title,
      errorMessage: u.errorMessage,
      updatedAt: u.updatedAt,
    }));
    lastFailureAt = failed[0]?.updatedAt ?? null;
  } catch (err) {
    console.error("ops_health_upload_failures_failed", err);
  }

  try {
    const lastOk = await db.upload.findFirst({
      where: { organizationId, deletedAt: null, status: "ingested" },
      orderBy: { updatedAt: "desc" },
      select: { updatedAt: true },
    });
    lastIngestedAt = lastOk?.updatedAt ?? null;
  } catch (err) {
    console.error("ops_health_last_ingested_failed", err);
  }

  try {
    const cutoff = new Date(Date.now() - STALE_MINUTES * 60 * 1000);
    const stale = await db.upload.findMany({
      where: {
        organizationId,
        deletedAt: null,
        status: { in: Array.from(TRANSIENT_STATUSES) },
        updatedAt: { lt: cutoff },
      },
      orderBy: { updatedAt: "asc" },
      take: 10,
      select: {
        id: true,
        title: true,
        status: true,
        updatedAt: true,
      },
    });
    const now = Date.now();
    staleInProgress = stale.map((u) => ({
      id: u.id,
      title: u.title,
      status: u.status as UploadStatus,
      updatedAt: u.updatedAt,
      minutesStuck: Math.round((now - u.updatedAt.getTime()) / 60000),
    }));
  } catch (err) {
    console.error("ops_health_stale_uploads_failed", err);
  }

  return {
    buckets,
    inFlight,
    queued,
    failed24h,
    lastIngestedAt,
    lastFailureAt,
    staleInProgress,
    recentFailures,
  };
}

async function loadTraceHealth() {
  let inFlight: TraceSummary[] = [];
  let recent: TraceSummary[] = [];
  let lastError: TraceSummary | null = null;
  let lastSuccess: TraceSummary | null = null;
  try {
    inFlight = await listInFlightTraces();
  } catch (err) {
    console.error("ops_health_in_flight_traces_failed", err);
  }
  try {
    recent = await listRecentTraces(25);
    lastError = recent.find((t) => t.status === "error") ?? null;
    lastSuccess = recent.find((t) => t.status === "ok") ?? null;
  } catch (err) {
    console.error("ops_health_recent_traces_failed", err);
  }
  return { inFlight, recent, lastError, lastSuccess };
}

async function loadAlertHealth() {
  let recent: AlertEventRow[] = [];
  try {
    recent = await listRecentAlerts(20);
  } catch (err) {
    console.error("ops_health_alerts_failed", err);
  }
  const unacknowledged = recent.filter((a) => !a.acknowledgedAt);
  return { recent, unacknowledged };
}

async function loadCurrentsBackend(): Promise<CurrentsBackend> {
  const url = (process.env.CURRENTS_API_URL ?? "http://127.0.0.1:8088").replace(/\/+$/, "");
  try {
    const health = await getCurrentsHealth({
      cache: "no-store",
      next: { revalidate: 0 },
    });
    return { reachable: true, error: null, health, url };
  } catch (err) {
    return {
      reachable: false,
      error: err instanceof Error ? err.message : String(err),
      health: null,
      url,
    };
  }
}

function loadAutoProcessingEnv(): AutoProcessingEnv {
  const repo = process.env.GITHUB_DISPATCH_REPO || "mrquintin/mqtheseuswork";
  return {
    githubDispatchToken: Boolean(process.env.GITHUB_DISPATCH_TOKEN),
    openaiKey: Boolean(process.env.OPENAI_API_KEY),
    anthropicKey: Boolean(process.env.ANTHROPIC_API_KEY),
    xBearerToken: process.env.X_BEARER_TOKEN
      ? true
      // Codex doesn't always set X_BEARER_TOKEN — the Currents backend
      // carries its own. We can't observe the backend's env from here,
      // so leave as null when we genuinely don't know, and rely on
      // `currents.health.x_bearer_present` for the authoritative answer.
      : null,
    githubDispatchRepo: repo,
    workflowUrl: `https://github.com/${repo}/actions/workflows/noosphere-process-uploads.yml`,
  };
}

function workflowCatalog(repo: string): WorkflowReference[] {
  const base = `https://github.com/${repo}/actions/workflows`;
  return [
    {
      name: "Noosphere — process Codex uploads",
      file: ".github/workflows/noosphere-process-uploads.yml",
      url: `${base}/noosphere-process-uploads.yml`,
      cadence: "repository_dispatch + every 10 min cron",
      purpose:
        "Drains the upload queue (extract, transcribe, claims), refreshes Currents, materializes Ops rollups.",
    },
    {
      name: "Build & deploy founder portal",
      file: ".github/workflows/build-founder-portal.yml",
      url: `${base}/build-founder-portal.yml`,
      cadence: "on push / manual",
      purpose: "Builds the Next.js founder portal image.",
    },
    {
      name: "Build Noosphere container",
      file: ".github/workflows/build-noosphere.yml",
      url: `${base}/build-noosphere.yml`,
      cadence: "on push / manual",
      purpose: "Builds the Noosphere worker image used by the always-on scheduler.",
    },
    {
      name: "Forecasts CI",
      file: ".github/workflows/forecasts-ci.yml",
      url: `${base}/forecasts-ci.yml`,
      cadence: "on push / pull request",
      purpose: "Smoke-tests the forecasts portfolio service.",
    },
    {
      name: "Nightly replication",
      file: ".github/workflows/nightly_replication.yml",
      url: `${base}/nightly_replication.yml`,
      cadence: "nightly cron",
      purpose: "Snapshots the Codex DB for offline reanalysis.",
    },
  ];
}

export async function loadOpsHealth(tenant: TenantContext): Promise<OpsHealth> {
  const [
    uploads,
    traces,
    alerts,
    embedding,
    currents,
  ] = await Promise.all([
    loadUploadHealth(tenant.organizationId),
    loadTraceHealth(),
    loadAlertHealth(),
    embeddingHealth(tenant.organizationId).catch((err) => {
      console.error("ops_health_embedding_failed", err);
      return null as EmbeddingHealth | null;
    }),
    loadCurrentsBackend(),
  ]);
  const autoProcessing = loadAutoProcessingEnv();
  const workflows = workflowCatalog(autoProcessing.githubDispatchRepo);

  // We can't introspect the scheduler container from Vercel directly,
  // but a recent successful Currents cycle is good evidence the
  // always-on loop is alive. A reachable backend with `last_cycle_at`
  // inside the last hour ⇒ provisioned. Otherwise unknown — never
  // assert "fixed".
  let schedulerProvisioned: boolean | "unknown" = "unknown";
  if (currents.reachable && currents.health?.last_cycle_at) {
    const last = Date.parse(currents.health.last_cycle_at);
    if (Number.isFinite(last)) {
      schedulerProvisioned = Date.now() - last < 60 * 60 * 1000;
    }
  } else if (!currents.reachable) {
    schedulerProvisioned = false;
  }

  return {
    generatedAt: new Date(),
    uploads,
    traces,
    alerts,
    embedding,
    currents,
    autoProcessing,
    workflows,
    schedulerProvisioned,
  };
}

export const STALE_THRESHOLD_MINUTES = STALE_MINUTES;
