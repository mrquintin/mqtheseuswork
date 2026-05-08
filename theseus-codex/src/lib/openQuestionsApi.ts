import { db } from "@/lib/db";

/**
 * OpenQuestion read/write surface for the founder triage queue and
 * the public methodology page.
 *
 * Two responsibilities:
 *
 *   1. Compute a bounded priority score for each `OpenQuestion`. The
 *      authoritative scorer is `noosphere/evaluation/question_priority.py`;
 *      this is its TS shadow, working from the columns Prisma actually
 *      stores. Same three-component philosophy:
 *
 *        - centrality      → how many existing conclusions reference
 *                            either of the two claims this question is
 *                            "about". Saturating curve so a 50-link
 *                            question doesn't drown a 5-link one.
 *        - replayability   → cheap proxy from `unresolvedReason` text:
 *                            "literature", "lookup", "ask" → cheap;
 *                            "rerun", "replicate", "embargo" → expensive.
 *        - calibration     → thinness of the firm's track record in the
 *                            question's domain (derived from the linked
 *                            claims' domains).
 *
 *      Weights are normalized so centrality alone cannot dominate the
 *      final score (the prompt's pinned constraint).
 *
 *   2. Strict public-visibility filter. A question is public-visible
 *      iff both of its linked claims have a `PublishedConclusion` row.
 *      Anything else is firm-internal triage and stays inside the
 *      founder workspace.
 */

export type OpenQuestionRow = {
  id: string;
  summary: string;
  unresolvedReason: string;
  layerDisagreementSummary: string;
  claimAId: string;
  claimBId: string;
  createdAt: Date;
};

export type DomainFootprint = {
  domain: string;
  resolvedForecastCount: number;
};

export type PriorityComponent = {
  name: "centrality" | "replayability" | "calibration_relevance";
  raw: number;
  weight: number;
  contribution: number;
};

export type PriorityScore = {
  questionId: string;
  score: number;
  components: PriorityComponent[];
};

export type TriageRow = OpenQuestionRow & {
  priority: PriorityScore;
  linkedConclusionCount: number;
  domain: string;
  candidateMethodNames: string[];
};

const DEFAULT_WEIGHTS = {
  centrality: 0.4,
  replayability: 0.3,
  calibration_relevance: 0.3,
} as const;

const CENTRALITY_SATURATION = 8;
const CALIBRATION_THICK_THRESHOLD = 30;

const CHEAP_RESOLUTION_HINTS = [
  "literature",
  "lookup",
  "reading",
  "cite",
  "ask",
  "search",
  "google",
  "documented",
];

const EXPENSIVE_RESOLUTION_HINTS = [
  "rerun",
  "replicate",
  "embargo",
  "year of",
  "long-horizon",
  "longitudinal",
  "experiment",
  "build a",
  "instrument",
];

function clip01(x: number): number {
  if (Number.isNaN(x)) return 0;
  if (x < 0) return 0;
  if (x > 1) return 1;
  return x;
}

function centralityScore(linkedConclusionCount: number): number {
  return clip01(linkedConclusionCount / CENTRALITY_SATURATION);
}

function replayabilityScore(reasonText: string): number {
  const text = (reasonText ?? "").toLowerCase();
  if (!text) return 0.5;
  let score = 0.5;
  for (const hint of CHEAP_RESOLUTION_HINTS) {
    if (text.includes(hint)) {
      score = Math.max(score, 0.85);
    }
  }
  for (const hint of EXPENSIVE_RESOLUTION_HINTS) {
    if (text.includes(hint)) {
      score = Math.min(score, 0.2);
    }
  }
  return clip01(score);
}

function calibrationRelevanceScore(footprint: DomainFootprint | null): number {
  if (!footprint) return 0.5;
  const thinness = clip01(
    1 - footprint.resolvedForecastCount / CALIBRATION_THICK_THRESHOLD,
  );
  return thinness;
}

export type ScoreInputs = {
  linkedConclusionCount: number;
  unresolvedReason: string;
  domainFootprint: DomainFootprint | null;
};

export function scoreOpenQuestion(
  questionId: string,
  inputs: ScoreInputs,
  weights: Partial<typeof DEFAULT_WEIGHTS> = {},
): PriorityScore {
  const w = { ...DEFAULT_WEIGHTS, ...weights };
  const sum = w.centrality + w.replayability + w.calibration_relevance;
  if (sum <= 0) {
    return scoreOpenQuestion(questionId, inputs, DEFAULT_WEIGHTS);
  }
  const norm = {
    centrality: w.centrality / sum,
    replayability: w.replayability / sum,
    calibration_relevance: w.calibration_relevance / sum,
  };

  const rawCentral = centralityScore(inputs.linkedConclusionCount);
  const rawReplay = replayabilityScore(inputs.unresolvedReason);
  const rawCalib = calibrationRelevanceScore(inputs.domainFootprint);

  const components: PriorityComponent[] = [
    {
      name: "centrality",
      raw: rawCentral,
      weight: norm.centrality,
      contribution: rawCentral * norm.centrality,
    },
    {
      name: "replayability",
      raw: rawReplay,
      weight: norm.replayability,
      contribution: rawReplay * norm.replayability,
    },
    {
      name: "calibration_relevance",
      raw: rawCalib,
      weight: norm.calibration_relevance,
      contribution: rawCalib * norm.calibration_relevance,
    },
  ];

  const score = clip01(
    components.reduce((acc, c) => acc + c.contribution, 0),
  );
  return { questionId, score, components };
}

// ── Triage queue (founder workspace) ───────────────────────────────────────

type ConclusionJoin = {
  id: string;
  domain: string | null;
  methodUsed: string | null;
};

async function loadLinkedClaimMap(
  organizationId: string,
  ids: string[],
): Promise<Map<string, ConclusionJoin>> {
  if (ids.length === 0) return new Map();
  const conclusions = await db.conclusion.findMany({
    where: { organizationId, id: { in: ids } },
    select: { id: true },
  });
  const knownIds = conclusions.map((c) => c.id);
  if (knownIds.length === 0) return new Map();
  const methods = await db.conclusionMethod.findMany({
    where: { organizationId, conclusionId: { in: knownIds } },
    select: {
      conclusionId: true,
      domain: true,
      methodName: true,
      weight: true,
    },
    orderBy: { weight: "desc" },
  });
  const byConclusion = new Map<string, ConclusionJoin>();
  for (const id of knownIds) {
    byConclusion.set(id, { id, domain: null, methodUsed: null });
  }
  for (const m of methods) {
    const existing = byConclusion.get(m.conclusionId);
    if (!existing) continue;
    if (!existing.domain && m.domain) existing.domain = m.domain;
    if (!existing.methodUsed && m.methodName) existing.methodUsed = m.methodName;
  }
  return byConclusion;
}

async function buildDomainFootprints(
  organizationId: string,
  domains: Iterable<string>,
): Promise<Map<string, DomainFootprint>> {
  const out = new Map<string, DomainFootprint>();
  const unique = Array.from(new Set([...domains].filter(Boolean)));
  if (unique.length === 0) return out;
  // Aggregate sample sizes across methods per domain. Thicker domains
  // (more resolved forecasts feeding any method) score lower on the
  // calibration-relevance component.
  const rows = await db.methodTrackRecord.findMany({
    where: { organizationId, domain: { in: unique } },
    select: { domain: true, sampleSize: true },
  });
  for (const d of unique) out.set(d, { domain: d, resolvedForecastCount: 0 });
  for (const r of rows) {
    const cur = out.get(r.domain);
    if (cur) cur.resolvedForecastCount += r.sampleSize;
  }
  return out;
}

function inferDomain(joins: ConclusionJoin[]): string {
  const counts = new Map<string, number>();
  for (const j of joins) {
    const d = (j.domain ?? "").trim();
    if (!d) continue;
    counts.set(d, (counts.get(d) ?? 0) + 1);
  }
  let best = "";
  let bestN = 0;
  for (const [d, n] of counts) {
    if (n > bestN) {
      best = d;
      bestN = n;
    }
  }
  return best;
}

export async function loadTriageQueue(
  organizationId: string,
  options: { domain?: string; limit?: number } = {},
): Promise<TriageRow[]> {
  const rows = await db.openQuestion.findMany({
    where: { organizationId },
    orderBy: { createdAt: "desc" },
    take: options.limit ?? 200,
  });

  const claimIds = Array.from(
    new Set(rows.flatMap((r) => [r.claimAId, r.claimBId])),
  );
  const claimMap = await loadLinkedClaimMap(organizationId, claimIds);

  const allDomains = new Set<string>();
  for (const r of rows) {
    const a = claimMap.get(r.claimAId);
    const b = claimMap.get(r.claimBId);
    for (const j of [a, b]) {
      if (j?.domain) allDomains.add(j.domain);
    }
  }
  const footprints = await buildDomainFootprints(organizationId, allDomains);

  const triage = rows.map((r) => {
    const a = claimMap.get(r.claimAId);
    const b = claimMap.get(r.claimBId);
    const linked = [a, b].filter(Boolean) as ConclusionJoin[];
    const domain = inferDomain(linked);
    const candidateMethods = Array.from(
      new Set(
        linked
          .map((j) => (j.methodUsed ?? "").trim())
          .filter((s): s is string => Boolean(s)),
      ),
    );
    const linkedConclusionCount = linked.length;
    const priority = scoreOpenQuestion(r.id, {
      linkedConclusionCount,
      unresolvedReason: r.unresolvedReason,
      domainFootprint: domain ? footprints.get(domain) ?? null : null,
    });
    return {
      id: r.id,
      summary: r.summary,
      unresolvedReason: r.unresolvedReason,
      layerDisagreementSummary: r.layerDisagreementSummary,
      claimAId: r.claimAId,
      claimBId: r.claimBId,
      createdAt: r.createdAt,
      priority,
      linkedConclusionCount,
      domain,
      candidateMethodNames: candidateMethods,
    } satisfies TriageRow;
  });

  const filtered = options.domain
    ? triage.filter((t) => t.domain === options.domain)
    : triage;
  return filtered.sort((a, b) => b.priority.score - a.priority.score);
}

export async function listOpenQuestionDomains(
  organizationId: string,
): Promise<string[]> {
  const rows = await db.openQuestion.findMany({
    where: { organizationId },
    select: { claimAId: true, claimBId: true },
  });
  const claimIds = Array.from(
    new Set(rows.flatMap((r) => [r.claimAId, r.claimBId])),
  );
  const claimMap = await loadLinkedClaimMap(organizationId, claimIds);
  const domains = new Set<string>();
  for (const r of rows) {
    const a = claimMap.get(r.claimAId);
    const b = claimMap.get(r.claimBId);
    for (const j of [a, b]) {
      if (j?.domain) domains.add(j.domain);
    }
  }
  return Array.from(domains).sort();
}

// ── Promote-to-research action ─────────────────────────────────────────────

export type PromoteResult = {
  researchSuggestionId: string;
};

export async function promoteOpenQuestionToResearch(
  organizationId: string,
  questionId: string,
  founderId?: string,
): Promise<PromoteResult> {
  const question = await db.openQuestion.findFirst({
    where: { id: questionId, organizationId },
  });
  if (!question) {
    throw new Error(`open question not found: ${questionId}`);
  }
  const created = await db.researchSuggestion.create({
    data: {
      organizationId,
      title: question.summary.slice(0, 240),
      summary: question.summary,
      rationale:
        question.unresolvedReason ||
        `Promoted from open question ${question.id}.`,
      readingUris: "[]",
      sessionLabel: "open-question",
      sourceUploadId: question.sourceUploadId,
      suggestedForFounderId: founderId,
    },
  });
  return { researchSuggestionId: created.id };
}

// ── Public surface ─────────────────────────────────────────────────────────

export type PublicOpenQuestion = {
  id: string;
  summary: string;
  createdAt: Date;
  domain: string;
  candidateMethodNames: string[];
  /**
   * Public-visible conclusion ids whose published confidence depends on
   * this question being resolved. Only `PublishedConclusion` rows are
   * surfaced; firm-internal claims are filtered out by construction.
   */
  gatedPublishedConclusionIds: string[];
};

/**
 * Strict public-visibility filter: a question is rendered publicly iff
 * BOTH of its linked claims have a `PublishedConclusion` row. The
 * symmetry is intentional — a question that touches one published claim
 * and one private internal claim is still firm-internal gossip and is
 * suppressed.
 */
export async function loadPublicOpenQuestions(
  organizationId: string,
  options: { limit?: number } = {},
): Promise<PublicOpenQuestion[]> {
  const rows = await db.openQuestion.findMany({
    where: { organizationId },
    orderBy: { createdAt: "desc" },
    take: options.limit ?? 80,
  });

  const claimIds = Array.from(
    new Set(rows.flatMap((r) => [r.claimAId, r.claimBId])),
  );
  if (claimIds.length === 0) return [];

  const claimMap = await loadLinkedClaimMap(organizationId, claimIds);

  const publishedRows = await db.publishedConclusion.findMany({
    where: {
      organizationId,
      sourceConclusionId: { in: claimIds },
    },
    select: { id: true, sourceConclusionId: true },
  });
  const publishedByClaim = new Map<string, string[]>();
  for (const p of publishedRows) {
    const existing = publishedByClaim.get(p.sourceConclusionId) ?? [];
    existing.push(p.id);
    publishedByClaim.set(p.sourceConclusionId, existing);
  }

  const out: PublicOpenQuestion[] = [];
  for (const r of rows) {
    const aPub = publishedByClaim.get(r.claimAId);
    const bPub = publishedByClaim.get(r.claimBId);
    if (!aPub || !bPub) continue; // strict filter
    const a = claimMap.get(r.claimAId);
    const b = claimMap.get(r.claimBId);
    const linked = [a, b].filter(Boolean) as ConclusionJoin[];
    const domain = inferDomain(linked);
    const candidates = Array.from(
      new Set(
        linked
          .map((j) => (j.methodUsed ?? "").trim())
          .filter((s): s is string => Boolean(s)),
      ),
    );
    out.push({
      id: r.id,
      summary: r.summary,
      createdAt: r.createdAt,
      domain,
      candidateMethodNames: candidates,
      gatedPublishedConclusionIds: [...aPub, ...bPub],
    });
  }
  return out;
}
