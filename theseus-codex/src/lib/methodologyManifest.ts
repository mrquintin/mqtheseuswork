import fs from "node:fs";
import path from "node:path";

import { Prisma } from "@prisma/client";

import { db } from "@/lib/db";
import { listCatalogs, publicModesForMethod } from "@/lib/failureModes";
import { MIN_PUBLISHABLE_SAMPLE } from "@/lib/methodTrackRecord";
import {
  MANIFEST_SCHEMA_VERSION,
  type ManifestCalibration,
  type ManifestDriftState,
  type ManifestEdge,
  type ManifestFailureMode,
  type ManifestMethod,
  type ManifestTrackRecord,
  type MethodologyManifest,
} from "@/lib/methodologyManifestShared";
export {
  driftColor,
  driftLabel,
  MANIFEST_SCHEMA_VERSION,
  type ManifestCalibration,
  type ManifestDriftState,
  type ManifestEdge,
  type ManifestFailureMode,
  type ManifestMethod,
  type ManifestTrackRecord,
  type MethodologyManifest,
} from "@/lib/methodologyManifestShared";

/**
 * Public methodology manifest — the single read-through layer the
 * `/methodology` explorer, the per-method tabs, and the
 * `/api/public/methodology/manifest` route all share.
 *
 * Visibility rule: every numeric field is derived from rows that are
 * already public (PublishedConclusion present, failure mode public,
 * sample size at or above the publish gate). Private rows do not enter
 * any aggregate.
 *
 * Schema version: the manifest payload carries the version as the
 * top-level `v` field; the public API route additionally surfaces it
 * as `meta.schemaVersion` on the envelope. Both flow from
 * `MANIFEST_SCHEMA_VERSION` in `methodologyManifestShared.ts`. Bumps
 * are a published-contract change — see
 * `docs/architecture/API_Envelope_Contract.md` for the rules.
 */
type GraphSnapshot = {
  schema?: string;
  nodes: Array<{
    name: string;
    depth: number;
    description: string;
    status: string;
    version: string;
  }>;
  edges: Array<{ src: string; dst: string }>;
};

function readGraphSnapshot(): GraphSnapshot | null {
  const candidates = [
    path.join(process.cwd(), "public", "method-graph.public.json"),
    path.join(process.cwd(), "public", "method-graph.json"),
  ];
  for (const p of candidates) {
    try {
      const text = fs.readFileSync(p, "utf8");
      return JSON.parse(text) as GraphSnapshot;
    } catch {
      // try next candidate
    }
  }
  return null;
}

function decimalToNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string") {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  if (typeof value === "object" && "toNumber" in (value as object)) {
    try {
      const n = (value as { toNumber: () => number }).toNumber();
      return Number.isFinite(n) ? n : null;
    } catch {
      return null;
    }
  }
  return null;
}

/**
 * Filesystem proxy for "last review date": the most recent mtime of a
 * method's RATIONALE.md or .py file. The firm reviews methods by
 * editing their rationale, so this tracks reviewer touch even when
 * the registry doesn't carry an explicit timestamp.
 */
function lastReviewDateForMethod(methodName: string): string | null {
  const env = process.env.NOOSPHERE_METHODS_DIR;
  const candidates: string[] = [];
  if (env) candidates.push(env);
  let cur = process.cwd();
  for (let i = 0; i < 6; i += 1) {
    candidates.push(path.join(cur, "noosphere", "noosphere", "methods"));
    const parent = path.dirname(cur);
    if (parent === cur) break;
    cur = parent;
  }
  for (const dir of candidates) {
    try {
      if (!fs.existsSync(dir)) continue;
      let best: number = 0;
      for (const ext of [".RATIONALE.md", ".py"]) {
        const p = path.join(dir, `${methodName}${ext}`);
        try {
          const stat = fs.statSync(p);
          if (stat.mtimeMs > best) best = stat.mtimeMs;
        } catch {
          // missing — skip
        }
      }
      if (best > 0) return new Date(best).toISOString();
    } catch {
      // try next candidate
    }
  }
  return null;
}

type DriftRow = { methodName: string; severity: string | null; observedAt: Date | string | null };

function reduceDrift(rows: DriftRow[]): { state: ManifestDriftState; lastActiveAt: string | null } {
  let state: ManifestDriftState = "ok";
  let consecutiveClean = 0;
  let lastActiveAt: string | null = null;
  const CLEAN_THRESHOLD = 2;
  for (const r of rows) {
    const sev = r.severity ?? "ok";
    const obs = r.observedAt
      ? typeof r.observedAt === "string"
        ? r.observedAt
        : r.observedAt.toISOString()
      : null;
    if (sev === "insufficient") {
      consecutiveClean = 0;
      continue;
    }
    if (sev === "escalate") {
      state = "escalate";
      consecutiveClean = 0;
      lastActiveAt = obs;
      continue;
    }
    if (sev === "warn") {
      consecutiveClean = 0;
      lastActiveAt = obs;
      if (state === "ok") state = "warn";
      continue;
    }
    if (state === "ok") continue;
    consecutiveClean += 1;
    if (consecutiveClean >= CLEAN_THRESHOLD) {
      state = "ok";
      consecutiveClean = 0;
    }
  }
  return { state, lastActiveAt };
}

async function fetchDriftByMethod(methodNames: string[]): Promise<Map<string, { state: ManifestDriftState; lastActiveAt: string | null }>> {
  const out = new Map<string, { state: ManifestDriftState; lastActiveAt: string | null }>();
  if (methodNames.length === 0) return out;
  type Row = { methodName: string; severity: string | null; observedAt: Date | string | null };
  let rows: Row[] = [];
  try {
    rows = await db.$queryRaw<Row[]>(
      Prisma.sql`SELECT "methodName", severity, "observedAt"
                   FROM "DriftEvent"
                  WHERE "targetKind" = 'method'
                    AND "methodName" IN (${Prisma.join(methodNames)})
                ORDER BY "methodName" ASC, "observedAt" ASC
                  LIMIT 5000`,
    );
  } catch {
    return out;
  }
  const grouped = new Map<string, Row[]>();
  for (const r of rows) {
    const arr = grouped.get(r.methodName) ?? [];
    arr.push(r);
    grouped.set(r.methodName, arr);
  }
  for (const [name, arr] of grouped.entries()) {
    out.set(name, reduceDrift(arr));
  }
  return out;
}

/**
 * Public conclusions-produced counts per method. Rows are joined to
 * `PublishedConclusion` so private conclusions are excluded.
 */
async function fetchPublicConclusionCounts(methodNames: string[]): Promise<Map<string, number>> {
  const out = new Map<string, number>();
  if (methodNames.length === 0) return out;
  type Row = { methodName: string; n: bigint | number };
  let rows: Row[] = [];
  try {
    rows = await db.$queryRaw<Row[]>(
      Prisma.sql`SELECT cm."methodName" AS "methodName",
                        COUNT(DISTINCT cm."conclusionId") AS n
                   FROM "ConclusionMethod" cm
                   JOIN "PublishedConclusion" pc
                     ON pc."sourceConclusionId" = cm."conclusionId"
                    AND pc."organizationId" = cm."organizationId"
                  WHERE cm."methodName" IN (${Prisma.join(methodNames)})
               GROUP BY cm."methodName"`,
    );
  } catch {
    return out;
  }
  for (const r of rows) {
    const n = typeof r.n === "bigint" ? Number(r.n) : Number(r.n);
    out.set(r.methodName, Number.isFinite(n) ? n : 0);
  }
  return out;
}

type RawTrackRecord = {
  organizationId: string;
  methodName: string;
  methodVersion: string;
  domain: string;
  sampleSize: number;
  weightedBrier: unknown;
  calibrationSlope: unknown;
  calibrationSlopeCiLow: unknown;
  calibrationSlopeCiHigh: unknown;
  severityPassRate: unknown;
  computedAt: Date;
};

async function fetchPublicTrackRecords(methodNames: string[]): Promise<RawTrackRecord[]> {
  if (methodNames.length === 0) return [];
  try {
    const rows = await db.methodTrackRecord.findMany({
      where: {
        methodName: { in: methodNames },
        sampleSize: { gte: MIN_PUBLISHABLE_SAMPLE },
      },
      orderBy: [{ methodName: "asc" }, { sampleSize: "desc" }],
    });
    return rows as unknown as RawTrackRecord[];
  } catch {
    return [];
  }
}

/** Pick the largest-n track record per method (across versions and domains). */
function pickHeadlineCalibration(records: RawTrackRecord[]): ManifestCalibration | null {
  if (records.length === 0) return null;
  let best: RawTrackRecord | null = null;
  for (const r of records) {
    if (!best || r.sampleSize > best.sampleSize) best = r;
  }
  if (!best) return null;
  const slope = decimalToNumber(best.calibrationSlope);
  if (slope === null) return null;
  return {
    slope,
    ciLow: decimalToNumber(best.calibrationSlopeCiLow),
    ciHigh: decimalToNumber(best.calibrationSlopeCiHigh),
    sampleSize: best.sampleSize,
    domain: best.domain,
    weightedBrier: decimalToNumber(best.weightedBrier),
    severityPassRate: decimalToNumber(best.severityPassRate),
  };
}

/**
 * Normalize a raw track-record row into the public manifest shape.
 * Org id is dropped because the public manifest is not multi-tenant.
 */
function normalizePublicRecord(r: RawTrackRecord): ManifestTrackRecord {
  return {
    method: r.methodName,
    version: r.methodVersion,
    domain: r.domain,
    sampleSize: r.sampleSize,
    calibrationSlope: decimalToNumber(r.calibrationSlope),
    calibrationSlopeCiLow: decimalToNumber(r.calibrationSlopeCiLow),
    calibrationSlopeCiHigh: decimalToNumber(r.calibrationSlopeCiHigh),
    weightedBrier: decimalToNumber(r.weightedBrier),
    severityPassRate: decimalToNumber(r.severityPassRate),
    computedAt: r.computedAt instanceof Date ? r.computedAt.toISOString() : String(r.computedAt),
  };
}

/**
 * Single source of truth for the explorer. Executes the joins and
 * filters once; the `/methodology` page, the per-method pages, and
 * the `/api/public/methodology/manifest` route all read this.
 */
export async function buildMethodologyManifest(): Promise<MethodologyManifest> {
  const snap = readGraphSnapshot();
  const nodes = snap?.nodes ?? [];
  const edges = snap?.edges ?? [];
  const methodNames = nodes.map((n) => n.name);

  const [counts, drift, trackRecords] = await Promise.all([
    fetchPublicConclusionCounts(methodNames),
    fetchDriftByMethod(methodNames),
    fetchPublicTrackRecords(methodNames),
  ]);

  const recordsByMethod = new Map<string, RawTrackRecord[]>();
  for (const r of trackRecords) {
    const arr = recordsByMethod.get(r.methodName) ?? [];
    arr.push(r);
    recordsByMethod.set(r.methodName, arr);
  }

  const methods: ManifestMethod[] = nodes.map((n) => {
    const records = recordsByMethod.get(n.name) ?? [];
    const calibration = pickHeadlineCalibration(records);
    const publicModes = publicModesForMethod(n.name);
    return {
      name: n.name,
      version: n.version,
      description: n.description,
      status: n.status,
      depth: n.depth,
      domain: calibration?.domain || null,
      conclusionsProduced: counts.get(n.name) ?? 0,
      calibration,
      drift: drift.get(n.name) ?? { state: "ok", lastActiveAt: null },
      publicFailureModeCount: publicModes.length,
      lastReviewDate: lastReviewDateForMethod(n.name),
    };
  });

  // Public failure modes: catalog modes flagged `public: true`. We
  // surface the same fields the per-method failures page already shows,
  // minus citations (those are richer on the page itself).
  const publicFailureModes: ManifestFailureMode[] = [];
  for (const cat of listCatalogs()) {
    if (cat.failures === "deliberately-empty") continue;
    for (const m of cat.modes) {
      if (!m.public) continue;
      publicFailureModes.push({
        method: cat.method,
        name: m.name,
        severity: m.severity,
        description: m.description,
        trigger: m.trigger_conditions,
        mitigation: m.mitigation,
      });
    }
  }

  const publicTrackRecords = trackRecords.map(normalizePublicRecord);

  // Pick the largest-n row per (method, version, domain) so that
  // multi-tenant rows collapse to one entry without re-aggregation.
  const recordKey = (r: ManifestTrackRecord) => `${r.method}::${r.version}::${r.domain}`;
  const collapsed = new Map<string, ManifestTrackRecord>();
  for (const r of publicTrackRecords) {
    const existing = collapsed.get(recordKey(r));
    if (!existing || r.sampleSize > existing.sampleSize) collapsed.set(recordKey(r), r);
  }

  return {
    v: MANIFEST_SCHEMA_VERSION,
    schema: "theseus.methodology.manifest",
    generatedAt: new Date().toISOString(),
    methods,
    edges,
    publicFailureModes,
    publicTrackRecords: Array.from(collapsed.values()).sort((a, b) => {
      if (a.method !== b.method) return a.method.localeCompare(b.method);
      if (a.version !== b.version) return b.version.localeCompare(a.version);
      return a.domain.localeCompare(b.domain);
    }),
  };
}

/** Convenience: fetch the manifest entry for a single method. */
export async function methodEntry(methodName: string): Promise<ManifestMethod | null> {
  const manifest = await buildMethodologyManifest();
  return manifest.methods.find((m) => m.name === methodName) ?? null;
}
