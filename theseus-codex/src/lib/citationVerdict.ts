/**
 * Shared types and presentation helpers for citation-chain verdicts.
 *
 * The verdict is the NLI judge's call on whether the cited source
 * actually supports the firm's stated claim. The four labels mirror
 * `noosphere/noosphere/literature/citation_chain.py::VerdictLabel`.
 *
 * The pill colors are picked to match the public reader's mental model:
 * green for "checks out", red for "the firm's own check disagrees with
 * its citation", gray for "the firm checked but the answer wasn't
 * clear-cut". Yellow (neutral) signals "the source is on-topic but
 * does not commit to the claim" — the gate treats this like
 * contradicts for `supports` cites, but the visual stays distinct.
 */

export type CitationRelation = "supports" | "contradicts" | "qualifies" | "mentions";

export type CitationVerdictLabel = "entails" | "contradicts" | "neutral" | "ambiguous";

export interface CitationVerdictPayload {
  /** "opinion" | "forecast" | "conclusion_source" */
  citation_kind: string;
  citation_id: string;
  source_id: string;
  relation: CitationRelation;
  relation_holds: CitationVerdictLabel;
  confidence: number;
  excerpt_used: string;
  stated_claim: string;
  cascade_weight: number;
  model_version: string;
  computed_at: string;
  overridden_by?: string | null;
  override_reason?: string | null;
}

export interface VerdictPillStyle {
  bg: string;
  fg: string;
  label: string;
  /** Aria/tooltip explanation a public reader sees. */
  description: string;
}

const STYLE: Record<CitationVerdictLabel, VerdictPillStyle> = {
  entails: {
    bg: "#1d3a1d",
    fg: "#bdf3bd",
    label: "Source checks out",
    description: "The firm's NLI judge found that the source excerpt entails the claim.",
  },
  contradicts: {
    bg: "#5b1414",
    fg: "#ffd1d1",
    label: "Source disagrees",
    description: "The firm's NLI judge found that the source excerpt contradicts the claim.",
  },
  neutral: {
    bg: "#5a4a14",
    fg: "#ffe9a8",
    label: "Source non-committal",
    description:
      "The source excerpt is on-topic but does not commit to the firm's claim.",
  },
  ambiguous: {
    bg: "#3a3a3a",
    fg: "#dcdcdc",
    label: "Verdict unsettled",
    description:
      "The firm's NLI judge could not pick a confident label. Recorded as a finding.",
  },
};

export function verdictPill(label: CitationVerdictLabel): VerdictPillStyle {
  return STYLE[label] ?? STYLE.ambiguous;
}

const VERDICT_LABELS = new Set<CitationVerdictLabel>([
  "entails",
  "contradicts",
  "neutral",
  "ambiguous",
]);

const RELATION_LABELS = new Set<CitationRelation>([
  "supports",
  "contradicts",
  "qualifies",
  "mentions",
]);

function isVerdictLabel(value: unknown): value is CitationVerdictLabel {
  return typeof value === "string" && VERDICT_LABELS.has(value as CitationVerdictLabel);
}

function isRelation(value: unknown): value is CitationRelation {
  return typeof value === "string" && RELATION_LABELS.has(value as CitationRelation);
}

/**
 * Coerce a raw payload (camelCase from Prisma or snake_case from the
 * Python validator) into a CitationVerdictPayload. Returns null if the
 * payload is missing required fields — callers render no pill in that
 * case rather than guessing a label.
 */
export function normalizeVerdictPayload(
  raw: unknown,
): CitationVerdictPayload | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const relation = r.relation;
  const label = r.relation_holds ?? r.relationHolds;
  if (!isRelation(relation) || !isVerdictLabel(label)) return null;
  return {
    citation_kind: String(r.citation_kind ?? r.citationKind ?? ""),
    citation_id: String(r.citation_id ?? r.citationId ?? ""),
    source_id: String(r.source_id ?? r.sourceId ?? ""),
    relation,
    relation_holds: label,
    confidence: Number(r.confidence ?? 0),
    excerpt_used: String(r.excerpt_used ?? r.excerptUsed ?? ""),
    stated_claim: String(r.stated_claim ?? r.statedClaim ?? ""),
    cascade_weight: Number(r.cascade_weight ?? r.cascadeWeight ?? 0),
    model_version: String(r.model_version ?? r.modelVersion ?? ""),
    computed_at: String(r.computed_at ?? r.computedAt ?? ""),
    overridden_by:
      (r.overridden_by as string | null | undefined) ??
      (r.overriddenById as string | null | undefined) ??
      null,
    override_reason:
      (r.override_reason as string | null | undefined) ??
      (r.overrideReason as string | null | undefined) ??
      null,
  };
}

/**
 * Public-reader summary line — short, complete sentence safe to drop
 * directly into the popover. Reflects the firm's own check, not the
 * source itself.
 */
export function verdictSummary(payload: CitationVerdictPayload): string {
  const pct = Math.round(Math.max(0, Math.min(1, payload.confidence)) * 100);
  if (payload.overridden_by && payload.override_reason) {
    return `Founder accepted with reason: ${payload.override_reason}`;
  }
  switch (payload.relation_holds) {
    case "entails":
      return `Firm's check: source supports this claim (${pct}% NLI confidence).`;
    case "contradicts":
      return `Firm's check: source disagrees with this claim (${pct}% NLI confidence).`;
    case "neutral":
      return `Firm's check: source is on-topic but does not commit to this claim.`;
    case "ambiguous":
    default:
      return `Firm's check: NLI judge could not confidently rule (max ${pct}%).`;
  }
}
