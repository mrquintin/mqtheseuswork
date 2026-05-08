import fs from "node:fs/promises";
import path from "node:path";

/**
 * Server-side reader for load-test result JSONs.
 *
 * The Python harness in `tests/load/article_viral.py` writes one
 * results file per run into `tests/load/results/`. This module is the
 * dashboard's only entry point into that directory — it parses, sorts,
 * and trims the run history into a shape the page can render directly.
 *
 * Why filesystem and not the database?  Two reasons:
 *
 *   1. The harness is dependency-free — it must run in a stripped-down
 *      CI image that doesn't have Prisma, the Codex schema, or DB
 *      credentials. Writing JSON keeps the harness narrow.
 *   2. The dashboard is read-only and trends don't need to be
 *      queryable past 90 days; CI artifacts already retain runs that
 *      long. Re-reading a small JSON directory each render is cheap.
 *
 * Files older than the per-profile retention are ignored at render
 * time but not deleted — CI keeps the source of truth.
 */

export type LoadProfileName = "light" | "viral" | "spike";

export type LoadVerdict = {
  passed: boolean;
  reasons: string[];
};

export type LoadStats = {
  total: number;
  errors: number;
  errorRate: number;
  p50Ms: number;
  p95Ms: number;
  p99Ms: number;
  poolExhaustionEvents: number;
  byPath: Record<
    string,
    { count: number; errors: number; p50_ms: number; p95_ms: number }
  >;
};

export type LoadBudget = {
  p50_ms: number;
  p95_ms: number;
  error_rate: number;
  max_pool_exhaustion_events: number;
};

export type LoadRun = {
  runId: string;
  profile: LoadProfileName;
  startedAt: string;
  finishedAt: string;
  baseUrl: string;
  articleSlug: string | null;
  samples: number;
  stats: LoadStats;
  budget: LoadBudget;
  verdict: LoadVerdict;
  overrideReason: string | null;
  filename: string;
};

const DEFAULT_RESULTS_DIR = path.resolve(
  process.cwd(),
  "..",
  "tests",
  "load",
  "results",
);

function resolveResultsDir(): string {
  return process.env.LOAD_TEST_RESULTS_DIR ?? DEFAULT_RESULTS_DIR;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asProfile(value: unknown): LoadProfileName {
  if (value === "viral" || value === "spike") return value;
  return "light";
}

/**
 * Parse one result file. Returns null if the file is malformed — the
 * caller skips it rather than aborting the whole dashboard render.
 *
 * Exported for unit testing the dashboard's parser independently of the
 * filesystem.
 */
export function parseLoadRun(
  filename: string,
  raw: unknown,
): LoadRun | null {
  if (!raw || typeof raw !== "object") return null;
  const root = raw as Record<string, unknown>;
  const stats = root.stats as Record<string, unknown> | undefined;
  const budget = root.budget as Record<string, unknown> | undefined;
  const verdict = root.verdict as Record<string, unknown> | undefined;
  if (!stats || !budget || !verdict) return null;

  const byPathRaw =
    (stats.byPath as Record<string, Record<string, number>> | undefined) ?? {};
  const byPath: LoadStats["byPath"] = {};
  for (const [key, val] of Object.entries(byPathRaw)) {
    byPath[key] = {
      count: asNumber(val.count),
      errors: asNumber(val.errors),
      p50_ms: asNumber(val.p50_ms),
      p95_ms: asNumber(val.p95_ms),
    };
  }

  const reasonsRaw = verdict.reasons;
  const reasons = Array.isArray(reasonsRaw)
    ? reasonsRaw.filter((r): r is string => typeof r === "string")
    : [];

  return {
    runId: asString(root.runId, filename),
    profile: asProfile(root.profile),
    startedAt: asString(root.startedAt),
    finishedAt: asString(root.finishedAt),
    baseUrl: asString(root.baseUrl),
    articleSlug:
      typeof root.articleSlug === "string" ? root.articleSlug : null,
    samples: asNumber(root.samples),
    stats: {
      total: asNumber(stats.total),
      errors: asNumber(stats.errors),
      errorRate: asNumber(stats.errorRate),
      p50Ms: asNumber(stats.p50Ms),
      p95Ms: asNumber(stats.p95Ms),
      p99Ms: asNumber(stats.p99Ms),
      poolExhaustionEvents: asNumber(stats.poolExhaustionEvents),
      byPath,
    },
    budget: {
      p50_ms: asNumber(budget.p50_ms),
      p95_ms: asNumber(budget.p95_ms),
      error_rate: asNumber(budget.error_rate),
      max_pool_exhaustion_events: asNumber(budget.max_pool_exhaustion_events),
    },
    verdict: {
      passed: Boolean(verdict.passed),
      reasons,
    },
    overrideReason:
      typeof root.overrideReason === "string" ? root.overrideReason : null,
    filename,
  };
}

/**
 * Read every results file from disk, parse, and sort newest first.
 * Limits to ``limit`` runs after sort. Robust to a missing directory
 * (returns []), unreadable files (skipped), and malformed JSON
 * (skipped).
 */
export async function listLoadRuns(limit = 50): Promise<LoadRun[]> {
  const dir = resolveResultsDir();
  let entries: string[];
  try {
    entries = await fs.readdir(dir);
  } catch {
    return [];
  }
  const runs: LoadRun[] = [];
  for (const entry of entries) {
    if (!entry.endsWith(".json")) continue;
    const full = path.join(dir, entry);
    let text: string;
    try {
      text = await fs.readFile(full, "utf-8");
    } catch {
      continue;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      continue;
    }
    const run = parseLoadRun(entry, parsed);
    if (run) runs.push(run);
  }
  runs.sort((a, b) => b.startedAt.localeCompare(a.startedAt));
  return runs.slice(0, limit);
}

export type LoadTrendPoint = {
  startedAt: string;
  p50Ms: number;
  p95Ms: number;
  errorRate: number;
  passed: boolean;
};

/**
 * Reduce a run list to a single trendline per profile. Oldest first
 * so the chart reads left-to-right.
 */
export function trendByProfile(
  runs: LoadRun[],
): Record<LoadProfileName, LoadTrendPoint[]> {
  const out: Record<LoadProfileName, LoadTrendPoint[]> = {
    light: [],
    viral: [],
    spike: [],
  };
  const ordered = [...runs].sort((a, b) =>
    a.startedAt.localeCompare(b.startedAt),
  );
  for (const run of ordered) {
    out[run.profile].push({
      startedAt: run.startedAt,
      p50Ms: run.stats.p50Ms,
      p95Ms: run.stats.p95Ms,
      errorRate: run.stats.errorRate,
      passed: run.verdict.passed,
    });
  }
  return out;
}
