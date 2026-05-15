/**
 * Methodology manifest schema version. Surfaced on
 * `/api/public/methodology/manifest` as both `meta.schemaVersion` and
 * the in-payload `v` field (the latter retained for legacy-alias
 * consumers — see `docs/architecture/API_Envelope_Contract.md`).
 *
 * External consumers pin against this; bumps require a changelog entry
 * in the envelope contract doc.
 *
 * v1 (2026-03): initial public release alongside the unified envelope.
 */
export const MANIFEST_SCHEMA_VERSION = 1;

export type ManifestDriftState = "ok" | "warn" | "escalate";

export type ManifestCalibration = {
  slope: number;
  ciLow: number | null;
  ciHigh: number | null;
  sampleSize: number;
  domain: string;
  weightedBrier: number | null;
  severityPassRate: number | null;
};

export type ManifestMethod = {
  name: string;
  version: string;
  description: string;
  status: string;
  depth: number;
  domain: string | null;
  conclusionsProduced: number;
  calibration: ManifestCalibration | null;
  drift: { state: ManifestDriftState; lastActiveAt: string | null };
  publicFailureModeCount: number;
  lastReviewDate: string | null;
};

export type ManifestEdge = { src: string; dst: string };

export type ManifestFailureMode = {
  method: string;
  name: string;
  severity: string;
  description: string;
  trigger: string;
  mitigation: string;
};

export type ManifestTrackRecord = {
  method: string;
  version: string;
  domain: string;
  sampleSize: number;
  calibrationSlope: number | null;
  calibrationSlopeCiLow: number | null;
  calibrationSlopeCiHigh: number | null;
  weightedBrier: number | null;
  severityPassRate: number | null;
  computedAt: string;
};

export type MethodologyManifest = {
  v: number;
  schema: "theseus.methodology.manifest";
  generatedAt: string;
  methods: ManifestMethod[];
  edges: ManifestEdge[];
  publicFailureModes: ManifestFailureMode[];
  publicTrackRecords: ManifestTrackRecord[];
};

export function driftLabel(state: ManifestDriftState): string {
  if (state === "escalate") return "Drifting";
  if (state === "warn") return "Watch";
  return "OK";
}

export function driftColor(state: ManifestDriftState): string {
  if (state === "escalate") return "var(--ember, #c0392b)";
  if (state === "warn") return "var(--amber, #d4a017)";
  return "var(--public-muted, #888)";
}
