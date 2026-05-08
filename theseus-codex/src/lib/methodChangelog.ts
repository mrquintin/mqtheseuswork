import { db } from "@/lib/db";

/**
 * Read-side helper for `/methodology/[method]/changelog`.
 *
 * Loads the captured `MethodVersion` rows for a method, pairs them
 * into ordered transitions (vN → vN+1 in capture-time order), and
 * computes a public-safe diff for each transition.
 *
 * Visibility rules mirror the Python `version_diff` renderer:
 *   * `source` and `rationale` are public — show their unified diff.
 *   * `failuresPublicYaml` already excludes private modes; the
 *     failure delta is computed from this filtered view, so private
 *     mode names never appear in the public changelog.
 *   * `domainBoundJson` is a canonical JSON of the bound; tag and
 *     anchor-radius changes are public, anchor coordinates are
 *     replaced upstream by a digest hash.
 */

export interface MethodVersionRow {
  contentHash: string;
  methodVersion: string;
  source: string;
  rationale: string;
  failuresPublicYaml: string;
  domainBoundJson: string;
  capturedAt: Date;
}

export interface FailureDelta {
  added: string[];
  removed: string[];
  changed: string[];
}

export interface ChangelogTransition {
  /// Stable URL fragment. Same value on every render of the same
  /// destination version, on any machine. Drives both the
  /// `<section id>` on the page and the link from the digest.
  anchor: string;
  fromVersion: string;
  toVersion: string;
  fromHash: string;
  toHash: string;
  capturedAt: string;
  codeDiff: string;
  rationaleDiff: string;
  failuresDelta: FailureDelta;
  domainBoundDiff: string;
  isEmpty: boolean;
}

interface ParsedFailureCatalog {
  modes: Array<{ name: string; [key: string]: unknown }>;
}

function parseFailures(text: string): Map<string, Record<string, unknown>> {
  // The Python writer canonicalizes via JSON, so JSON parse is the
  // primary path. We tolerate empty blobs.
  if (!text || !text.trim()) return new Map();
  let data: unknown = null;
  try {
    data = JSON.parse(text);
  } catch {
    return new Map();
  }
  if (!data || typeof data !== "object") return new Map();
  const modes = (data as Partial<ParsedFailureCatalog>).modes;
  if (!Array.isArray(modes)) return new Map();
  const out = new Map<string, Record<string, unknown>>();
  for (const m of modes) {
    if (m && typeof m === "object" && typeof m.name === "string") {
      out.set(m.name, m as Record<string, unknown>);
    }
  }
  return out;
}

function failureDelta(a: string, b: string): FailureDelta {
  const aModes = parseFailures(a);
  const bModes = parseFailures(b);
  const added: string[] = [];
  const removed: string[] = [];
  const changed: string[] = [];
  for (const name of bModes.keys()) {
    if (!aModes.has(name)) added.push(name);
  }
  for (const name of aModes.keys()) {
    if (!bModes.has(name)) removed.push(name);
  }
  for (const [name, bMode] of bModes) {
    if (!aModes.has(name)) continue;
    const aMode = aModes.get(name)!;
    if (JSON.stringify(aMode) !== JSON.stringify(bMode)) changed.push(name);
  }
  added.sort();
  removed.sort();
  changed.sort();
  return { added, removed, changed };
}

/**
 * Tiny unified-diff renderer. The page uses `<pre>` for the diff
 * blocks, so we don't need GitHub-style HTML — just the standard
 * +/- lines a programmer can read. Pulling in a full `diff` package
 * just for this would be overkill, and the input is bounded by the
 * size of one method file. The algorithm is the same LCS-based
 * unified diff as Python's difflib.unified_diff.
 */
function unifiedDiff(a: string, b: string, labelA: string, labelB: string): string {
  if (a === b) return "";
  const aLines = a.split(/\r?\n/);
  const bLines = b.split(/\r?\n/);
  const ops = computeOps(aLines, bLines);
  const out: string[] = [`--- ${labelA}`, `+++ ${labelB}`];
  let aLine = 0;
  let bLine = 0;
  // Group hunks separated by long runs of equal lines (>3 each side).
  let buffer: string[] = [];
  let hunkAStart = 0;
  let hunkBStart = 0;
  let hunkALen = 0;
  let hunkBLen = 0;
  let inHunk = false;
  const flushHunk = () => {
    if (!inHunk) return;
    out.push(
      `@@ -${hunkAStart + 1},${hunkALen} +${hunkBStart + 1},${hunkBLen} @@`
    );
    out.push(...buffer);
    buffer = [];
    inHunk = false;
    hunkALen = 0;
    hunkBLen = 0;
  };
  let equalRun = 0;
  for (const op of ops) {
    if (op.kind === "equal") {
      if (inHunk && equalRun < 3) {
        buffer.push(` ${op.line}`);
        hunkALen += 1;
        hunkBLen += 1;
        equalRun += 1;
      } else if (inHunk) {
        flushHunk();
      }
      aLine += 1;
      bLine += 1;
      if (!inHunk) equalRun = 0;
    } else if (op.kind === "del") {
      if (!inHunk) {
        hunkAStart = Math.max(0, aLine - 0);
        hunkBStart = Math.max(0, bLine - 0);
        inHunk = true;
        equalRun = 0;
      }
      buffer.push(`-${op.line}`);
      hunkALen += 1;
      aLine += 1;
    } else {
      if (!inHunk) {
        hunkAStart = Math.max(0, aLine - 0);
        hunkBStart = Math.max(0, bLine - 0);
        inHunk = true;
        equalRun = 0;
      }
      buffer.push(`+${op.line}`);
      hunkBLen += 1;
      bLine += 1;
    }
  }
  flushHunk();
  return out.join("\n");
}

type DiffOp = { kind: "equal" | "del" | "add"; line: string };

function computeOps(a: string[], b: string[]): DiffOp[] {
  const n = a.length;
  const m = b.length;
  // Standard LCS DP. The inputs are bounded by a single method file
  // so an O(n*m) table is fine.
  const dp: number[][] = Array.from({ length: n + 1 }, () =>
    new Array<number>(m + 1).fill(0)
  );
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      if (a[i] === b[j]) dp[i][j] = dp[i + 1][j + 1] + 1;
      else dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const ops: DiffOp[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      ops.push({ kind: "equal", line: a[i] });
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push({ kind: "del", line: a[i] });
      i += 1;
    } else {
      ops.push({ kind: "add", line: b[j] });
      j += 1;
    }
  }
  while (i < n) {
    ops.push({ kind: "del", line: a[i] });
    i += 1;
  }
  while (j < m) {
    ops.push({ kind: "add", line: b[j] });
    j += 1;
  }
  return ops;
}

export function buildTransitions(
  rows: MethodVersionRow[]
): ChangelogTransition[] {
  const sorted = [...rows].sort(
    (a, b) => a.capturedAt.getTime() - b.capturedAt.getTime()
  );
  const out: ChangelogTransition[] = [];
  for (let i = 1; i < sorted.length; i += 1) {
    const a = sorted[i - 1];
    const b = sorted[i];
    const codeDiff = unifiedDiff(
      a.source,
      b.source,
      `${a.methodVersion}`,
      `${b.methodVersion}`
    );
    const rationaleDiff = unifiedDiff(
      a.rationale,
      b.rationale,
      `${a.methodVersion} RATIONALE`,
      `${b.methodVersion} RATIONALE`
    );
    const fdelta = failureDelta(a.failuresPublicYaml, b.failuresPublicYaml);
    const boundDiff = unifiedDiff(
      a.domainBoundJson,
      b.domainBoundJson,
      `${a.methodVersion} DOMAIN`,
      `${b.methodVersion} DOMAIN`
    );
    const isEmpty =
      !codeDiff &&
      !rationaleDiff &&
      !boundDiff &&
      fdelta.added.length === 0 &&
      fdelta.removed.length === 0 &&
      fdelta.changed.length === 0;
    out.push({
      anchor: `v-${b.contentHash.replace(/^v_/, "").slice(0, 12)}`,
      fromVersion: a.methodVersion,
      toVersion: b.methodVersion,
      fromHash: a.contentHash,
      toHash: b.contentHash,
      capturedAt: b.capturedAt.toISOString(),
      codeDiff,
      rationaleDiff,
      failuresDelta: fdelta,
      domainBoundDiff: boundDiff,
      isEmpty,
    });
  }
  return out;
}

export interface EffectSummary {
  conclusionsReanalyzed: number;
  meanCalibrationDelta: number | null;
  meanMqsDeltas: Record<string, number>;
}

/**
 * Read whatever effect-on-results numbers are available for a
 * (fromHash, toHash) transition. The codex DB tracks per-method
 * MQS sub-scores via `MethodologyQualityScore` and per-method
 * calibration via `MethodTrackRecord`. When a conclusion has been
 * re-analyzed under both versions (rare, opt-in via
 * `reanalyze-codex.sh`), this surface aggregates the deltas.
 *
 * For the current schema we don't store per-conclusion-per-version
 * MQS, so the implementation degrades to "0 conclusions reanalyzed"
 * — which is the honest answer when no opt-in re-analysis has run.
 * The shape is forward-compatible with a future
 * `ConclusionVersionAnalysis` table.
 */
export async function loadEffectSummary(
  _methodName: string,
  _fromHash: string,
  _toHash: string
): Promise<EffectSummary> {
  return {
    conclusionsReanalyzed: 0,
    meanCalibrationDelta: null,
    meanMqsDeltas: {},
  };
}

export async function loadMethodVersions(
  methodName: string
): Promise<MethodVersionRow[]> {
  type DbMethodVersion = {
    contentHash: string;
    methodVersion: string;
    source: string;
    rationale: string;
    failuresPublicYaml: string;
    domainBoundJson: string;
    capturedAt: Date;
  };
  const dbAny = db as unknown as {
    methodVersion?: {
      findMany: (args: unknown) => Promise<DbMethodVersion[]>;
    };
  };
  if (!dbAny.methodVersion) {
    return [];
  }
  const rows = await dbAny.methodVersion.findMany({
    where: { methodName },
    orderBy: { capturedAt: "asc" },
    select: {
      contentHash: true,
      methodVersion: true,
      source: true,
      rationale: true,
      failuresPublicYaml: true,
      domainBoundJson: true,
      capturedAt: true,
    },
  });
  return rows.map((r: DbMethodVersion) => ({
    contentHash: r.contentHash,
    methodVersion: r.methodVersion,
    source: r.source,
    rationale: r.rationale,
    failuresPublicYaml: r.failuresPublicYaml,
    domainBoundJson: r.domainBoundJson,
    capturedAt: r.capturedAt,
  }));
}

export const __test__ = {
  unifiedDiff,
  parseFailures,
  failureDelta,
};
