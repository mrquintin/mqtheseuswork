/**
 * Cross-surface search ranker.
 *
 * The firm's knowledge surfaces — principles, conclusions, claims —
 * used to rank by text match alone, which buried the principles
 * (slogans are short; conclusions and claims are longer and tend to
 * win on raw substring scoring). Round 21 reorganises the surface so
 * principles are the spine: when a reader searches a phrase, the
 * principles it matches are the answer, with conclusions and claims as
 * supporting layers.
 *
 * This module is the ranking layer only — it does not crawl any data
 * source, mint any index, or replace the per-surface query paths. The
 * upstream caller is responsible for assembling candidate
 * `SearchCandidate` rows from whichever store it owns. `rankResults`
 * scores each candidate by a cheap textual match and then applies a
 * type-stratified bonus that pushes principles above conclusions above
 * claims for any non-zero match.
 *
 * The stratification is intentional: a tied text score across types is
 * resolved in favour of the higher tier (principle > conclusion >
 * claim), so principle slogans never get pushed below conclusion prose
 * by length-correlated noise.
 */

export type SearchCandidateKind = "principle" | "conclusion" | "claim";

export type SearchCandidate = {
  id: string;
  kind: SearchCandidateKind;
  text: string;
  /**
   * Optional href the caller wants attached to the result. The ranker
   * passes it through unchanged.
   */
  href?: string;
};

export type SearchResult = SearchCandidate & {
  /** Final ranking score, descending. */
  score: number;
  /** Underlying textual-match score, before the type-tier bonus. */
  textScore: number;
};

/**
 * Tier bonuses. The gap between tiers is wider than any plausible text-
 * score difference (text scores are in [0, 1]), so the ordering is
 * principles → conclusions → claims regardless of length-noise in the
 * textual match.
 */
const TIER_BONUS: Record<SearchCandidateKind, number> = {
  principle: 1_000_000,
  conclusion: 1_000,
  claim: 1,
};

function normalize(text: string): string {
  return text.toLowerCase().trim();
}

function tokenize(text: string): string[] {
  return normalize(text)
    .split(/[^a-z0-9]+/u)
    .filter((token) => token.length > 0);
}

/**
 * Cheap, dependency-free text scoring.
 *
 * Returns 0 if the query has no tokens or none of them appear in the
 * candidate text. Otherwise returns the fraction of query tokens that
 * matched, biased slightly by a substring boost so a phrase that
 * appears verbatim outranks the same tokens scattered across the text.
 */
export function textScore(query: string, candidateText: string): number {
  const queryTokens = tokenize(query);
  if (queryTokens.length === 0) return 0;
  const target = normalize(candidateText);
  if (!target) return 0;

  let hits = 0;
  for (const token of queryTokens) {
    if (target.includes(token)) hits += 1;
  }
  const coverage = hits / queryTokens.length;
  if (coverage === 0) return 0;

  // Verbatim-phrase boost — capped so it cannot dominate the coverage
  // term, but enough to break ties between candidates that match the
  // same tokens.
  const phraseBoost = target.includes(normalize(query)) ? 0.15 : 0;
  return Math.min(1, coverage + phraseBoost);
}

/**
 * Rank `candidates` against `query`. Principles outrank conclusions
 * outrank claims for any non-zero match; within a tier the higher text
 * score wins, ties broken by insertion order (stable sort).
 *
 * Candidates with a zero text score are dropped. An empty query
 * returns no results (the caller should fall back to the un-filtered
 * surface; this module does not invent listings).
 */
export function rankResults(
  query: string,
  candidates: ReadonlyArray<SearchCandidate>,
): SearchResult[] {
  const normalizedQuery = query.trim();
  if (!normalizedQuery) return [];

  const scored: SearchResult[] = [];
  for (const candidate of candidates) {
    const t = textScore(normalizedQuery, candidate.text);
    if (t === 0) continue;
    scored.push({
      ...candidate,
      textScore: t,
      score: t + TIER_BONUS[candidate.kind],
    });
  }
  // Stable sort: JS Array.prototype.sort is stable as of ES2019.
  scored.sort((a, b) => b.score - a.score);
  return scored;
}
