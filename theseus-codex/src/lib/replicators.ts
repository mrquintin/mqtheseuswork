/**
 * Replicators page data loader.
 *
 * The `/methodology/replicators` page lists outside researchers who
 * have run the firm's replication harness and produced a signed
 * reproducibility certificate. The list is sourced from JSON
 * certificates that the firm has signed; each certificate is one row.
 *
 * Where the certificates live
 * ---------------------------
 * Two directories are searched, in order:
 *
 *   1. `replication/certificates/` at the repo root (where the firm
 *      keeps the canonical, signed copies).
 *   2. `theseus-codex/public/replication-certificates/` (a public
 *      mirror under the web app, useful for previews and for
 *      shipping certificates with the static build).
 *
 * Either is fine; the first wins on duplicate filenames. A missing
 * directory is not an error — the page just renders empty, and the
 * empty state explains "no certified replications yet".
 *
 * What this loader does NOT do
 * ----------------------------
 * It does NOT verify Ed25519 signatures. Signature verification lives
 * in the Python module `replication.lib.certificate.verify_certificate`
 * and is performed at the time the firm signs / accepts a
 * certificate. The web layer treats the on-disk certificate as
 * already-trusted: the threat is not a forged certificate landing in
 * the public mirror (which is the firm's own git tree), it is the
 * firm accidentally publishing a certificate whose canonical hash
 * doesn't match its signature. That check belongs in CI, not in the
 * page renderer.
 *
 * What this loader DOES enforce
 * -----------------------------
 *   - `replicatorConsentPublic === true`. Certificates without
 *     consent are filtered out of the public list. The certificate
 *     still exists on disk; it just doesn't render.
 *   - The schema field matches `theseus.replicationCertificate.v1`.
 *     A future schema bump is a public-contract change and the
 *     loader returns an explicit "unsupported schema" entry so the
 *     page can surface the mismatch instead of silently dropping
 *     rows.
 */

import fs from "node:fs";
import path from "node:path";

export const REPLICATION_CERTIFICATE_SCHEMA =
  "theseus.replicationCertificate.v1";

/**
 * The subset of a certificate's signed payload that the public page
 * actually renders. We intentionally narrow the surface so a future
 * field added to the certificate (and signed in the canonical payload)
 * does not implicitly leak onto the page.
 */
export type ReplicatorRow = {
  /** Filename (without extension) used as a stable React key. */
  id: string;
  /** Researcher's claimed display name. Not verified by the firm. */
  name: string;
  /** Free-text affiliation as the replicator typed it. */
  affiliation: string;
  /** Benchmark version the replication covers — e.g. `qh-v1`. */
  benchmarkVersion: string;
  /** The runner whose numbers were verified. */
  runner: string;
  /** Models present in the run envelope (sorted). */
  models: string[];
  /** Whether the run was deterministic-mode. */
  deterministic: boolean;
  /** ISO-8601 timestamp the firm signed the certificate. */
  signedAt: string;
  /** Short fingerprint of the firm key that signed it. */
  keyFingerprint: string;
  /** Truncated canonical hash (12 hex chars) for quick visual diff. */
  canonicalHashShort: string;
  /** Replicator-recorded git SHA (informational; can differ from firm). */
  replicatorGitSha: string;
  /** Replicator platform string from the envelope. */
  platform: string;
  /** Python version the replicator ran. */
  pythonVersion: string;
  /** Free-text notes the firm or replicator chose to publish. */
  notes: string;
};

export type ReplicatorsLoad = {
  rows: ReplicatorRow[];
  /** Count of on-disk certificates the loader filtered for any reason. */
  filteredCount: number;
  /** Specific filter reasons, useful for the page's "audit trail" footer. */
  filterReasons: string[];
};

/**
 * Resolve where the loader should look for certificates. Exposed as a
 * function rather than a top-level constant so tests can override the
 * paths via `process.cwd()` redirection.
 */
function resolveSearchDirs(): string[] {
  const cwd = process.cwd();
  // We don't know whether cwd is the web-app root or the repo root at
  // build time; resolving both keeps the loader robust to either.
  const repoRoot = path.resolve(cwd, "..");
  return [
    path.join(repoRoot, "replication", "certificates"),
    path.join(cwd, "public", "replication-certificates"),
    path.join(cwd, "replication-certificates"),
  ];
}

type RawCertificate = {
  schema?: string;
  benchmarkVersion?: string;
  runnerSet?: string[];
  models?: string[];
  deterministic?: boolean;
  signedAt?: string;
  signatureHex?: string;
  canonicalHash?: string;
  keyFingerprint?: string;
  replicatorEnvelopeGitSha?: string;
  replicatorPlatform?: string;
  replicatorPythonVersion?: string;
  replicatorName?: string;
  replicatorAffiliation?: string;
  replicatorConsentPublic?: boolean;
  notes?: string;
};

function toRow(filename: string, raw: RawCertificate): ReplicatorRow {
  const id = filename.replace(/\.json$/i, "");
  return {
    id,
    name: (raw.replicatorName ?? "").trim() || "Anonymous replicator",
    affiliation: (raw.replicatorAffiliation ?? "").trim(),
    benchmarkVersion: raw.benchmarkVersion ?? "",
    runner: (raw.runnerSet ?? [])[0] ?? "",
    models: Array.from(raw.models ?? []).sort(),
    deterministic: Boolean(raw.deterministic),
    signedAt: raw.signedAt ?? "",
    keyFingerprint: raw.keyFingerprint ?? "",
    canonicalHashShort: (raw.canonicalHash ?? "").slice(0, 12),
    replicatorGitSha: (raw.replicatorEnvelopeGitSha ?? "").slice(0, 12),
    platform: raw.replicatorPlatform ?? "",
    pythonVersion: raw.replicatorPythonVersion ?? "",
    notes: (raw.notes ?? "").trim(),
  };
}

/**
 * Load the public replicators list.
 *
 * Errors are absorbed so a malformed certificate cannot break the
 * whole page; the count of dropped certificates is returned alongside
 * the rows so the page footer can disclose "N certificates filtered".
 */
export function loadReplicators(
  searchDirs: string[] = resolveSearchDirs(),
): ReplicatorsLoad {
  const seen = new Set<string>();
  const rows: ReplicatorRow[] = [];
  const filterReasons: string[] = [];
  let filteredCount = 0;

  for (const dir of searchDirs) {
    let entries: string[];
    try {
      if (!fs.existsSync(dir)) continue;
      entries = fs.readdirSync(dir);
    } catch {
      continue;
    }
    for (const filename of entries) {
      if (!filename.toLowerCase().endsWith(".json")) continue;
      if (seen.has(filename)) continue;
      seen.add(filename);
      const fullPath = path.join(dir, filename);
      let raw: RawCertificate;
      try {
        const text = fs.readFileSync(fullPath, "utf8");
        raw = JSON.parse(text) as RawCertificate;
      } catch (err) {
        filteredCount += 1;
        filterReasons.push(
          `${filename}: could not parse as JSON (${(err as Error).message})`,
        );
        continue;
      }
      if (raw.schema && raw.schema !== REPLICATION_CERTIFICATE_SCHEMA) {
        filteredCount += 1;
        filterReasons.push(
          `${filename}: unsupported schema ${JSON.stringify(raw.schema)}`,
        );
        continue;
      }
      if (!raw.replicatorConsentPublic) {
        filteredCount += 1;
        filterReasons.push(`${filename}: replicator did not consent to public credit`);
        continue;
      }
      if (!raw.signatureHex || !raw.canonicalHash || !raw.keyFingerprint) {
        // An unsigned certificate (e.g. one staged by the replicator
        // before the firm signed it) is not a public row.
        filteredCount += 1;
        filterReasons.push(`${filename}: missing signature; not yet signed by firm`);
        continue;
      }
      rows.push(toRow(filename, raw));
    }
  }

  // Newest first by signed timestamp; falls back to id for stable
  // ordering when timestamps are equal/missing.
  rows.sort((a, b) => {
    if (a.signedAt !== b.signedAt) {
      return a.signedAt < b.signedAt ? 1 : -1;
    }
    return a.id < b.id ? -1 : 1;
  });

  return { rows, filteredCount, filterReasons };
}
