import fs from "node:fs/promises";
import path from "node:path";

/**
 * Server-side CI health reader.
 *
 * Fetches workflow + run data from the GitHub REST API using the same
 * `GITHUB_DISPATCH_TOKEN` the upload trigger uses (see
 * `triggerNoosphereProcessing.ts`). Caches calls in memory for a
 * short window so a dashboard refresh does not blow through the
 * authenticated rate limit (5,000/hr per token).
 *
 * The dashboard at `/ops/ci` is the only consumer. It reads:
 *
 *   - One row per workflow file the firm cares about.
 *   - For each workflow: latest run status, p50 wall-clock time over
 *     the last N runs, observed flake rate over the same window.
 *   - The quarantine list parsed from `.github/workflows/_quarantine.md`,
 *     so quarantined workflows render with an explicit banner instead
 *     of a misleading "all green".
 *
 * No DB writes; no client-side calls. The page is rendered with
 * `dynamic = 'force-dynamic'` so each load hits this module fresh
 * (modulo the in-process cache).
 */

const DEFAULT_REPO = "mrquintin/mqtheseuswork";
const CACHE_TTL_MS = 60_000;
const RUN_SAMPLE_LIMIT = 30;

export type WorkflowRunConclusion =
  | "success"
  | "failure"
  | "cancelled"
  | "skipped"
  | "neutral"
  | "timed_out"
  | "action_required"
  | "stale"
  | "startup_failure"
  | null;

export type WorkflowRunStatus =
  | "queued"
  | "in_progress"
  | "completed"
  | "waiting"
  | "requested";

export type WorkflowSummary = {
  id: number;
  name: string;
  filename: string;
  state: string;
  htmlUrl: string;
};

export type WorkflowRun = {
  id: number;
  status: WorkflowRunStatus;
  conclusion: WorkflowRunConclusion;
  createdAt: string;
  updatedAt: string;
  durationMs: number;
  htmlUrl: string;
  headBranch: string | null;
  event: string;
};

export type WorkflowHealth = {
  workflow: WorkflowSummary;
  latest: WorkflowRun | null;
  /** "green" if latest non-cancelled run succeeded; "red" if it failed; "unknown" if no runs. */
  status: "green" | "red" | "unknown" | "in_progress";
  /** Median wall-clock duration in milliseconds across recent completed runs. 0 if no samples. */
  p50DurationMs: number;
  /** Fraction of recent runs whose conclusion was "failure". 0..1. */
  flakeRate: number;
  /** Number of completed runs sampled. */
  sampleSize: number;
  quarantine: QuarantineEntry | null;
};

export type QuarantineEntry = {
  workflow: string;
  entered: string;
  deadline: string;
  failureRate: number;
  reason: string;
  owner: string;
};

export type CIDashboard = {
  generatedAt: string;
  repo: string;
  configured: boolean;
  reason: string | null;
  workflows: WorkflowHealth[];
  quarantine: QuarantineEntry[];
};

const cache = new Map<string, { value: unknown; expiresAt: number }>();

function cacheGet<T>(key: string): T | null {
  const hit = cache.get(key);
  if (!hit) return null;
  if (hit.expiresAt < Date.now()) {
    cache.delete(key);
    return null;
  }
  return hit.value as T;
}

function cacheSet(key: string, value: unknown): void {
  cache.set(key, { value, expiresAt: Date.now() + CACHE_TTL_MS });
}

function ghToken(): string | null {
  return process.env.GITHUB_DISPATCH_TOKEN ?? null;
}

function ghRepo(): string {
  return process.env.GITHUB_DISPATCH_REPO || DEFAULT_REPO;
}

async function ghFetch<T>(pathPart: string): Promise<T> {
  const token = ghToken();
  if (!token) {
    throw new Error("GITHUB_DISPATCH_TOKEN not set");
  }
  const url = `https://api.github.com${pathPart}`;
  const cached = cacheGet<T>(url);
  if (cached) return cached;
  const res = await fetch(url, {
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "theseus-codex-ops-dashboard",
    },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`GitHub API ${res.status} for ${pathPart}`);
  }
  const data = (await res.json()) as T;
  cacheSet(url, data);
  return data;
}

type RawWorkflow = {
  id: number;
  name: string;
  path: string;
  state: string;
  html_url: string;
};

type RawRun = {
  id: number;
  status: WorkflowRunStatus;
  conclusion: WorkflowRunConclusion;
  created_at: string;
  updated_at: string;
  run_started_at?: string | null;
  html_url: string;
  head_branch: string | null;
  event: string;
};

function toWorkflow(raw: RawWorkflow): WorkflowSummary {
  return {
    id: raw.id,
    name: raw.name,
    filename: raw.path.replace(/^\.github\/workflows\//, ""),
    state: raw.state,
    htmlUrl: raw.html_url,
  };
}

function toRun(raw: RawRun): WorkflowRun {
  const start = raw.run_started_at ?? raw.created_at;
  const end = raw.updated_at;
  const durationMs = Math.max(
    0,
    new Date(end).getTime() - new Date(start).getTime(),
  );
  return {
    id: raw.id,
    status: raw.status,
    conclusion: raw.conclusion,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    durationMs,
    htmlUrl: raw.html_url,
    headBranch: raw.head_branch,
    event: raw.event,
  };
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? Math.round((sorted[mid - 1] + sorted[mid]) / 2)
    : sorted[mid];
}

export async function listWorkflows(): Promise<WorkflowSummary[]> {
  const repo = ghRepo();
  const data = await ghFetch<{ workflows: RawWorkflow[] }>(
    `/repos/${repo}/actions/workflows?per_page=100`,
  );
  return data.workflows
    // Reusable workflows live under `_*.yml`. They are non-runnable
    // and surface as state=active with zero runs; hide them from the
    // dashboard so the table is "things that actually run on PRs".
    .filter((w) => !w.path.match(/\/_[^/]+\.yml$/))
    .map(toWorkflow)
    .sort((a, b) => a.name.localeCompare(b.name));
}

export async function listWorkflowRuns(
  workflowId: number,
  limit = RUN_SAMPLE_LIMIT,
): Promise<WorkflowRun[]> {
  const repo = ghRepo();
  const data = await ghFetch<{ workflow_runs: RawRun[] }>(
    `/repos/${repo}/actions/workflows/${workflowId}/runs?per_page=${limit}`,
  );
  return data.workflow_runs.map(toRun);
}

function statusFor(latest: WorkflowRun | null): WorkflowHealth["status"] {
  if (!latest) return "unknown";
  if (latest.status !== "completed") return "in_progress";
  if (latest.conclusion === "success") return "green";
  if (latest.conclusion === "failure" || latest.conclusion === "timed_out") {
    return "red";
  }
  // cancelled / skipped / neutral don't flip the gate either way; show
  // the most recent meaningful run instead.
  return "unknown";
}

export function computeHealth(
  workflow: WorkflowSummary,
  runs: WorkflowRun[],
  quarantine: QuarantineEntry | null,
): WorkflowHealth {
  // Find the latest meaningful run for the status column — skip
  // cancelled/skipped runs because they don't signal health either way.
  const meaningful = runs.find(
    (r) =>
      r.status === "completed" &&
      r.conclusion !== "cancelled" &&
      r.conclusion !== "skipped",
  ) ?? runs[0] ?? null;
  const completed = runs.filter((r) => r.status === "completed");
  const failures = completed.filter((r) => r.conclusion === "failure").length;
  const successes = completed.filter((r) => r.conclusion === "success");
  return {
    workflow,
    latest: meaningful,
    status: statusFor(meaningful),
    p50DurationMs: median(successes.map((r) => r.durationMs)),
    flakeRate: completed.length === 0 ? 0 : failures / completed.length,
    sampleSize: completed.length,
    quarantine,
  };
}

const QUARANTINE_PATH = path.resolve(
  process.cwd(),
  "..",
  ".github",
  "workflows",
  "_quarantine.md",
);

/**
 * Parse `.github/workflows/_quarantine.md` for active entries.
 *
 * Tolerant: returns `[]` if the file is missing or only contains
 * the header. The schema is documented in the file itself.
 */
export async function loadQuarantine(): Promise<QuarantineEntry[]> {
  const filePath = process.env.CI_QUARANTINE_PATH ?? QUARANTINE_PATH;
  let raw: string;
  try {
    raw = await fs.readFile(filePath, "utf8");
  } catch {
    return [];
  }
  // Only parse the "## Active quarantine" section so historical entries
  // (which use a different shape) don't pollute the active list.
  const activeMatch = raw.match(
    /##\s+Active quarantine([\s\S]*?)(?:\n##\s+|$)/i,
  );
  const body = activeMatch ? activeMatch[1] : "";
  const entries: QuarantineEntry[] = [];
  // Each block is a sequence of `key: value` lines, separated by
  // blank lines. We don't enforce a fenced format; the parser walks
  // line-by-line and accumulates until it sees a blank line.
  const lines = body.split(/\r?\n/);
  let current: Partial<QuarantineEntry> & { _seen: number } = { _seen: 0 };
  const flush = () => {
    if (
      current.workflow &&
      current.entered &&
      current.deadline &&
      current.reason
    ) {
      entries.push({
        workflow: current.workflow,
        entered: current.entered,
        deadline: current.deadline,
        failureRate: current.failureRate ?? 0,
        reason: current.reason,
        owner: current.owner ?? "unassigned",
      });
    }
    current = { _seen: 0 };
  };
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || trimmed.startsWith("<!--")) {
      if (current._seen > 0) flush();
      continue;
    }
    const m = trimmed.match(/^([a-z_]+):\s*(.+)$/i);
    if (!m) continue;
    const [, key, value] = m;
    const k = key.toLowerCase();
    if (k === "workflow") current.workflow = value;
    else if (k === "entered") current.entered = value;
    else if (k === "deadline") current.deadline = value;
    else if (k === "failure_rate") current.failureRate = Number(value);
    else if (k === "reason") current.reason = value;
    else if (k === "owner") current.owner = value;
    current._seen += 1;
  }
  if (current._seen > 0) flush();
  return entries;
}

/**
 * Build the dashboard payload. Returns `configured: false` with a
 * reason instead of throwing when the token is missing — the page
 * renders an empty state instead of a 500.
 */
export async function getCIDashboard(): Promise<CIDashboard> {
  const repo = ghRepo();
  if (!ghToken()) {
    return {
      generatedAt: new Date().toISOString(),
      repo,
      configured: false,
      reason: "GITHUB_DISPATCH_TOKEN env var is not set on this deploy.",
      workflows: [],
      quarantine: await loadQuarantine(),
    };
  }
  const [workflows, quarantine] = await Promise.all([
    listWorkflows(),
    loadQuarantine(),
  ]);
  const quarantineByFile = new Map(quarantine.map((q) => [q.workflow, q]));
  // Run requests in parallel but cap concurrency so we don't burst
  // the rate limit on first cold load.
  const healths: WorkflowHealth[] = [];
  const concurrency = 4;
  for (let i = 0; i < workflows.length; i += concurrency) {
    const batch = workflows.slice(i, i + concurrency);
    const settled = await Promise.all(
      batch.map(async (wf) => {
        try {
          const runs = await listWorkflowRuns(wf.id);
          return computeHealth(wf, runs, quarantineByFile.get(wf.filename) ?? null);
        } catch {
          return computeHealth(wf, [], quarantineByFile.get(wf.filename) ?? null);
        }
      }),
    );
    healths.push(...settled);
  }
  return {
    generatedAt: new Date().toISOString(),
    repo,
    configured: true,
    reason: null,
    workflows: healths,
    quarantine,
  };
}
