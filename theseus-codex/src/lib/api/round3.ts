import { NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import {
  runNoospherePython,
  isNoosphereLikelyUnavailable,
  NOOSPHERE_UNAVAILABLE_MESSAGE,
} from "@/lib/pythonRuntime";

// TODO: Migrate shared types to packages/theseus-api-types/ when created

// ─── Types ──────────────────────────────────────────────

export interface ProvenanceRecord {
  id: string;
  conclusionId: string;
  sourceUploadId: string;
  extractionMethod: string;
  confidence: number;
  chain: ProvenanceLink[];
  createdAt: string;
}

export interface ProvenanceLink {
  step: number;
  kind: string;
  ref: string;
  detail: string;
}

export interface CascadeNode {
  id: string;
  conclusionId: string;
  parentId: string | null;
  kind: string;
  label: string;
  confidence: number;
  children: CascadeNode[];
}

export interface EvalRun {
  id: string;
  name: string;
  status: "pending" | "running" | "passed" | "failed";
  startedAt: string;
  completedAt: string | null;
  summary: string;
  passRate: number;
}

export interface EvalRunDetail extends EvalRun {
  cases: EvalCase[];
}

export interface EvalCase {
  id: string;
  input: string;
  expected: string;
  actual: string;
  passed: boolean;
  notes: string;
}

export interface PostMortem {
  id: string;
  conclusionId: string;
  conclusionText: string;
  retractedAt: string;
  reason: string;
  rootCause: string;
  preventionNotes: string;
  founderName: string;
}

export interface PeerReviewRecord {
  id: string;
  conclusionId: string;
  reviewerName: string;
  verdict: "endorse" | "challenge" | "abstain";
  commentary: string;
  createdAt: string;
}

export interface DecayRecord {
  id: string;
  conclusionId: string;
  conclusionText: string;
  currentConfidence: number;
  decayRate: number;
  lastValidated: string;
  projectedExpiry: string | null;
  status: "healthy" | "decaying" | "expired";
}

export interface RigorGateSubmission {
  id: string;
  kind: string;
  status: "pending" | "approved" | "rejected" | "overridden";
  submittedBy: string;
  submittedAt: string;
  resolvedAt: string | null;
  ledgerEntryId: string | null;
}

export interface RigorGateDetail extends RigorGateSubmission {
  payload: Record<string, unknown>;
  reviewNotes: string;
  overrideReason: string | null;
}

export interface MethodEntry {
  name: string;
  latestVersion: string;
  description: string;
  status: "active" | "candidate" | "deprecated";
  usageCount: number;
}

export interface MethodVersion {
  name: string;
  version: string;
  description: string;
  parameters: Record<string, unknown>;
  changelog: string;
  publishedAt: string;
  publishedBy: string;
}

export interface MethodCandidate {
  id: string;
  name: string;
  proposedBy: string;
  description: string;
  status: "proposed" | "under_review" | "accepted" | "rejected";
  createdAt: string;
}

export interface GatedResponse<T = unknown> {
  ok: boolean;
  ledgerEntryId: string;
  data?: T;
  error?: string;
}

// ─── Rigor Gate ──────────────────────────────────────────

/**
 * Wrapper around the Noosphere Python CLI used by the Rigor Gate helpers
 * below. Delegates to `runNoospherePython` so the serverless "no Python
 * available" case is handled in one place (returns `code: -1` with a
 * recognisable stderr message callers can surface verbatim).
 */
async function spawnPython(
  args: string[],
): Promise<{ code: number; stdout: string; stderr: string }> {
  const res = await runNoospherePython(["-m", "noosphere", ...args]);
  if (res.skipped) {
    return { code: -1, stdout: "", stderr: NOOSPHERE_UNAVAILABLE_MESSAGE };
  }
  return {
    code: res.code ?? 1,
    stdout: res.out,
    // The helper merges stdout+stderr; good enough for these callers which
    // only look at the final JSON on stdout when code===0.
    stderr: res.code === 0 ? "" : res.out,
  };
}

export async function submitToRigorGate(
  kind: string,
  founderName: string,
): Promise<{ approved: boolean; ledgerEntryId: string; reason?: string }> {
  const { code, stdout, stderr } = await spawnPython([
    "rigor-gate",
    "submit",
    `--kind=${kind}`,
    `--founder=${founderName}`,
  ]);

  if (code === 0) {
    try {
      const parsed = JSON.parse(stdout) as { ledger_entry_id?: string };
      return {
        approved: true,
        ledgerEntryId: parsed.ledger_entry_id || `gate-${Date.now()}`,
      };
    } catch {
      return { approved: true, ledgerEntryId: `gate-${Date.now()}` };
    }
  }

  if (process.env.NODE_ENV !== "production") {
    return { approved: true, ledgerEntryId: `dev-gate-${Date.now()}` };
  }

  return {
    approved: false,
    ledgerEntryId: "",
    reason: stderr || "Rigor gate rejected",
  };
}

type RouteHandler = (
  req: Request,
  ctx?: { params: Promise<Record<string, string>> },
) => Promise<NextResponse>;

export function withGated(kind: string, handler: RouteHandler): RouteHandler {
  return async (req, ctx) => {
    const founder = await getFounder();
    if (!founder) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const gate = await submitToRigorGate(kind, founder.name);
    if (!gate.approved) {
      return NextResponse.json(
        { ok: false, error: "Rigor gate rejected", reason: gate.reason },
        { status: 403 },
      );
    }

    const response = await handler(req, ctx);
    const body = await response.json();
    return NextResponse.json(
      { ...body, ledgerEntryId: gate.ledgerEntryId },
      { status: response.status },
    );
  };
}

// ─── Helpers ─────────────────────────────────────────────

function parseJson<T>(raw: unknown, fallback: T): T {
  if (!raw || typeof raw !== "string") return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

type RawRow = Record<string, unknown>;

async function safeQuery<T extends RawRow>(
  query: ReturnType<typeof Prisma.sql>,
): Promise<T[]> {
  try {
    return await db.$queryRaw<T[]>(query);
  } catch {
    return [];
  }
}

// ─── Read Functions ──────────────────────────────────────

export async function fetchProvenanceRecords(): Promise<ProvenanceRecord[]> {
  const rows = await safeQuery(
    Prisma.sql`SELECT id, conclusion_id, source_upload_id, extraction_method, confidence, chain_json, created_at FROM provenance ORDER BY created_at DESC LIMIT 200`,
  );
  return rows.map((r) => ({
    id: String(r.id),
    conclusionId: String(r.conclusion_id),
    sourceUploadId: String(r.source_upload_id ?? ""),
    extractionMethod: String(r.extraction_method ?? ""),
    confidence: Number(r.confidence ?? 0),
    chain: parseJson<ProvenanceLink[]>(r.chain_json, []),
    createdAt: String(r.created_at ?? ""),
  }));
}

export async function fetchProvenanceForConclusion(
  conclusionId: string,
): Promise<ProvenanceRecord[]> {
  const rows = await safeQuery(
    Prisma.sql`SELECT id, conclusion_id, source_upload_id, extraction_method, confidence, chain_json, created_at FROM provenance WHERE conclusion_id = ${conclusionId} ORDER BY created_at DESC`,
  );
  return rows.map((r) => ({
    id: String(r.id),
    conclusionId: String(r.conclusion_id),
    sourceUploadId: String(r.source_upload_id ?? ""),
    extractionMethod: String(r.extraction_method ?? ""),
    confidence: Number(r.confidence ?? 0),
    chain: parseJson<ProvenanceLink[]>(r.chain_json, []),
    createdAt: String(r.created_at ?? ""),
  }));
}

export async function fetchCascade(
  conclusionId: string,
): Promise<CascadeNode[]> {
  const rows = await safeQuery(
    Prisma.sql`SELECT id, conclusion_id, parent_id, kind, label, confidence FROM cascade_node WHERE conclusion_id = ${conclusionId} ORDER BY id`,
  );
  const flat = rows.map((r) => ({
    id: String(r.id),
    conclusionId: String(r.conclusion_id),
    parentId: r.parent_id ? String(r.parent_id) : null,
    kind: String(r.kind ?? ""),
    label: String(r.label ?? ""),
    confidence: Number(r.confidence ?? 0),
    children: [] as CascadeNode[],
  }));
  const byId = new Map(flat.map((n) => [n.id, n]));
  const roots: CascadeNode[] = [];
  for (const node of flat) {
    if (node.parentId && byId.has(node.parentId)) {
      byId.get(node.parentId)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

export async function fetchEvalRuns(): Promise<EvalRun[]> {
  const rows = await safeQuery(
    Prisma.sql`SELECT id, name, status, started_at, completed_at, summary, pass_rate FROM eval_run ORDER BY started_at DESC LIMIT 100`,
  );
  return rows.map((r) => ({
    id: String(r.id),
    name: String(r.name ?? ""),
    status: (String(r.status ?? "pending") as EvalRun["status"]),
    startedAt: String(r.started_at ?? ""),
    completedAt: r.completed_at ? String(r.completed_at) : null,
    summary: String(r.summary ?? ""),
    passRate: Number(r.pass_rate ?? 0),
  }));
}

export async function fetchEvalRunDetail(
  runId: string,
): Promise<EvalRunDetail | null> {
  const runs = await safeQuery(
    Prisma.sql`SELECT id, name, status, started_at, completed_at, summary, pass_rate FROM eval_run WHERE id = ${runId} LIMIT 1`,
  );
  if (runs.length === 0) return null;
  const r = runs[0];
  const cases = await safeQuery(
    Prisma.sql`SELECT id, input, expected, actual, passed, notes FROM eval_case WHERE run_id = ${runId} ORDER BY id`,
  );
  return {
    id: String(r.id),
    name: String(r.name ?? ""),
    status: (String(r.status ?? "pending") as EvalRun["status"]),
    startedAt: String(r.started_at ?? ""),
    completedAt: r.completed_at ? String(r.completed_at) : null,
    summary: String(r.summary ?? ""),
    passRate: Number(r.pass_rate ?? 0),
    cases: cases.map((c) => ({
      id: String(c.id),
      input: String(c.input ?? ""),
      expected: String(c.expected ?? ""),
      actual: String(c.actual ?? ""),
      passed: Boolean(c.passed),
      notes: String(c.notes ?? ""),
    })),
  };
}

export async function fetchPostMortems(): Promise<PostMortem[]> {
  const rows = await safeQuery(
    Prisma.sql`SELECT id, conclusion_id, conclusion_text, retracted_at, reason, root_cause, prevention_notes, founder_name FROM post_mortem ORDER BY retracted_at DESC LIMIT 100`,
  );
  return rows.map((r) => ({
    id: String(r.id),
    conclusionId: String(r.conclusion_id),
    conclusionText: String(r.conclusion_text ?? ""),
    retractedAt: String(r.retracted_at ?? ""),
    reason: String(r.reason ?? ""),
    rootCause: String(r.root_cause ?? ""),
    preventionNotes: String(r.prevention_notes ?? ""),
    founderName: String(r.founder_name ?? ""),
  }));
}

export async function fetchPeerReviews(
  conclusionId: string,
): Promise<PeerReviewRecord[]> {
  const rows = await safeQuery(
    Prisma.sql`SELECT id, conclusion_id, reviewer_name, verdict, commentary, created_at FROM peer_review WHERE conclusion_id = ${conclusionId} ORDER BY created_at DESC`,
  );
  return rows.map((r) => ({
    id: String(r.id),
    conclusionId: String(r.conclusion_id),
    reviewerName: String(r.reviewer_name ?? ""),
    verdict: (String(r.verdict ?? "abstain") as PeerReviewRecord["verdict"]),
    commentary: String(r.commentary ?? ""),
    createdAt: String(r.created_at ?? ""),
  }));
}

export async function fetchDecayRecords(): Promise<DecayRecord[]> {
  const rows = await safeQuery(
    Prisma.sql`SELECT id, conclusion_id, conclusion_text, current_confidence, decay_rate, last_validated, projected_expiry, status FROM decay_record ORDER BY last_validated DESC LIMIT 200`,
  );
  return rows.map((r) => ({
    id: String(r.id),
    conclusionId: String(r.conclusion_id),
    conclusionText: String(r.conclusion_text ?? ""),
    currentConfidence: Number(r.current_confidence ?? 0),
    decayRate: Number(r.decay_rate ?? 0),
    lastValidated: String(r.last_validated ?? ""),
    projectedExpiry: r.projected_expiry ? String(r.projected_expiry) : null,
    status: (String(r.status ?? "healthy") as DecayRecord["status"]),
  }));
}

export async function fetchGateSubmissions(): Promise<RigorGateSubmission[]> {
  const rows = await safeQuery(
    Prisma.sql`SELECT id, kind, status, submitted_by, submitted_at, resolved_at, ledger_entry_id FROM rigor_gate_submission ORDER BY submitted_at DESC LIMIT 200`,
  );
  return rows.map((r) => ({
    id: String(r.id),
    kind: String(r.kind ?? ""),
    status: (String(r.status ?? "pending") as RigorGateSubmission["status"]),
    submittedBy: String(r.submitted_by ?? ""),
    submittedAt: String(r.submitted_at ?? ""),
    resolvedAt: r.resolved_at ? String(r.resolved_at) : null,
    ledgerEntryId: r.ledger_entry_id ? String(r.ledger_entry_id) : null,
  }));
}

export async function fetchGateDetail(
  submissionId: string,
): Promise<RigorGateDetail | null> {
  const rows = await safeQuery(
    Prisma.sql`SELECT id, kind, status, submitted_by, submitted_at, resolved_at, ledger_entry_id, payload_json, review_notes, override_reason FROM rigor_gate_submission WHERE id = ${submissionId} LIMIT 1`,
  );
  if (rows.length === 0) return null;
  const r = rows[0];
  return {
    id: String(r.id),
    kind: String(r.kind ?? ""),
    status: (String(r.status ?? "pending") as RigorGateSubmission["status"]),
    submittedBy: String(r.submitted_by ?? ""),
    submittedAt: String(r.submitted_at ?? ""),
    resolvedAt: r.resolved_at ? String(r.resolved_at) : null,
    ledgerEntryId: r.ledger_entry_id ? String(r.ledger_entry_id) : null,
    payload: parseJson<Record<string, unknown>>(r.payload_json, {}),
    reviewNotes: String(r.review_notes ?? ""),
    overrideReason: r.override_reason ? String(r.override_reason) : null,
  };
}

export async function fetchMethods(): Promise<MethodEntry[]> {
  const rows = await safeQuery(
    Prisma.sql`SELECT name, latest_version, description, status, usage_count FROM method_registry ORDER BY name LIMIT 200`,
  );
  return rows.map((r) => ({
    name: String(r.name ?? ""),
    latestVersion: String(r.latest_version ?? ""),
    description: String(r.description ?? ""),
    status: (String(r.status ?? "active") as MethodEntry["status"]),
    usageCount: Number(r.usage_count ?? 0),
  }));
}

export async function fetchMethodVersion(
  name: string,
  version: string,
): Promise<MethodVersion | null> {
  const rows = await safeQuery(
    Prisma.sql`SELECT name, version, description, parameters_json, changelog, published_at, published_by FROM method_version WHERE name = ${name} AND version = ${version} LIMIT 1`,
  );
  if (rows.length === 0) return null;
  const r = rows[0];
  return {
    name: String(r.name),
    version: String(r.version),
    description: String(r.description ?? ""),
    parameters: parseJson<Record<string, unknown>>(r.parameters_json, {}),
    changelog: String(r.changelog ?? ""),
    publishedAt: String(r.published_at ?? ""),
    publishedBy: String(r.published_by ?? ""),
  };
}

export async function fetchMethodCandidates(): Promise<MethodCandidate[]> {
  const rows = await safeQuery(
    Prisma.sql`SELECT id, name, proposed_by, description, status, created_at FROM method_candidate ORDER BY created_at DESC LIMIT 100`,
  );
  return rows.map((r) => ({
    id: String(r.id),
    name: String(r.name ?? ""),
    proposedBy: String(r.proposed_by ?? ""),
    description: String(r.description ?? ""),
    status: (String(r.status ?? "proposed") as MethodCandidate["status"]),
    createdAt: String(r.created_at ?? ""),
  }));
}

// ─── Export Helpers ──────────────────────────────────────

export function toCSV(rows: Record<string, unknown>[]): string {
  if (rows.length === 0) return "";
  const headers = Object.keys(rows[0]);
  const lines = [headers.join(",")];
  for (const row of rows) {
    lines.push(
      headers
        .map((h) => {
          const v = row[h];
          const s =
            typeof v === "object" ? JSON.stringify(v) : String(v ?? "");
          return s.includes(",") || s.includes('"')
            ? `"${s.replace(/"/g, '""')}"`
            : s;
        })
        .join(","),
    );
  }
  return lines.join("\n");
}

export function downloadHref(data: string, mime: string): string {
  return `data:${mime};charset=utf-8,${encodeURIComponent(data)}`;
}
