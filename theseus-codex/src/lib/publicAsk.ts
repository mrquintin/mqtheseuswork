import { createHash } from "crypto";

import { db } from "@/lib/db";
import { resolvePublicOrganizationId } from "@/lib/conclusionsRead";
import { loadPublicOpenQuestions } from "@/lib/openQuestionsApi";

/**
 * Public inquiry retrieval.
 *
 * Powers `POST /api/public/ask` and the `/ask` page. The contract:
 *
 *   - Read-only. No generation, no rewriting. Snippets are extracted
 *     from the source body verbatim.
 *   - Visibility-bounded. We only see what `PublishedConclusion`
 *     surfaces publicly + non-revoked `EventOpinion` rows from the
 *     public org + the strict `loadPublicOpenQuestions` filter. The
 *     same filters every other public surface uses.
 *   - Bucket-grouped. Results split into conclusions, opinions,
 *     articles, open questions; the UI renders each rail.
 *   - Honest about silence. When nothing clears the relevance
 *     threshold, `noResult` flips and the closest open question is
 *     attached so the page can show "the firm has not addressed this
 *     directly" without going blank.
 *
 * Ranking is keyword-overlap with IDF weighting plus a small
 * title-bonus. The Python module `noosphere/inference/public_retrieval.py`
 * pins the embedding-driven equivalent that the firm's tests assert
 * against; this TS path mirrors its kind-bucketing, threshold logic,
 * snippet-extraction contract, query-class routing, MMR diversity, and
 * freshness signal so a future cutover to a Currents embedding service
 * is wire-level only.
 *
 * Round 17 prompt 28 added four things on top of first-version
 * retrieval:
 *   - Query understanding: `classifyQuery` routes each query into one
 *     of five classes (factual-claim, methodology-question,
 *     prediction-request, counter-argument-request, browse). Routing
 *     here is rule-based only — the live route has a 1.5s p50 budget
 *     and no freeform generation; the Python module carries the
 *     optional light LLM judge for the offline/Currents path.
 *   - Diverse retrieval: Maximum Marginal Relevance per rail, so the
 *     top results are not five paraphrases of one conclusion.
 *   - Honest empty result: the no-result branch carries both the
 *     closest open question AND the closest related conclusion.
 *   - Freshness: every result carries its date and an `isCurrent`
 *     flag. Stale conclusions are surfaced as stale, never silently
 *     de-ranked.
 *
 * Why TF-IDF here rather than embeddings? The Postgres rows that back
 * this surface (`PublishedConclusion`, `EventOpinion`, `OpenQuestion`)
 * do not store SBERT vectors today — only the noosphere graph does, and
 * pulling the graph into the Next.js worker would mean cold-start cost
 * on every public hit. Token overlap is what `/api/ask` already runs
 * against the same corpus and is trivially cacheable. The kind/threshold
 * contract is what readers see; the scoring metric beneath is an
 * implementation detail callers can swap.
 */

// ── Tunables ───────────────────────────────────────────────────────────────

/**
 * Result-quality threshold. A normalised score below this is treated
 * as "the firm has not addressed this directly" and fires the
 * no-result fallback. The constant is in [0, 1] over the IDF-weighted
 * cosine analogue we compute below.
 */
export const NO_RESULT_THRESHOLD = 0.18;

/**
 * Borderline band. When the top score sits inside [lower, upper) we
 * still render the result but we also surface "did you mean…"
 * rephrasings drawn from the next-best items.
 */
export const BORDERLINE_LOWER = NO_RESULT_THRESHOLD;
export const BORDERLINE_UPPER = 0.32;

/** Per-kind cap returned to the client. */
const TOP_PER_KIND = 5;

/** Snippet width in characters. Extractive only. */
const SNIPPET_CHARS = 240;

/** Cap raw query length to keep token math bounded. */
const MAX_QUERY_LEN = 500;

/** Minimum query length we'll bother retrieving against. */
const MIN_QUERY_LEN = 3;

/** Title-match bonus: matches in the title get this multiplier. */
const TITLE_BOOST = 1.4;

/**
 * Maximum Marginal Relevance tradeoff. λ weights pure relevance;
 * (1 − λ) weights dissimilarity from the items already picked. The
 * default favours relevance but keeps a meaningful diversity component
 * so a rail is not five paraphrases of one conclusion. Per-class
 * profiles override this (see `CLASS_PROFILES`).
 */
export const MMR_LAMBDA_DEFAULT = 0.7;

/**
 * A conclusion older than this — with no explicit "still current"
 * signal — is shown with a "stale" pill. Staleness is surfaced to the
 * reader; it is never used to silently de-rank a result.
 */
const FRESHNESS_STALE_DAYS = 365;

// ── Public types ───────────────────────────────────────────────────────────

export type PublicAskKind = "conclusion" | "opinion" | "article" | "open_question";

/**
 * Query-understanding class. Each class has its own retrieval profile
 * (kind ordering, per-kind boost, MMR λ) and its own rendering path in
 * `PublicAskBox`. Mirrors `noosphere/inference/query_classifier.py`.
 */
export type PublicAskQueryClass =
  | "factual-claim"
  | "methodology-question"
  | "prediction-request"
  | "counter-argument-request"
  | "browse";

export type PublicAskResult = {
  id: string;
  kind: PublicAskKind;
  title: string;
  href: string;
  snippet: string;
  /** [0, 1] relative score within the response. */
  relevance: number;
  /** Stated public confidence (raw), where the kind has one. */
  confidence: number | null;
  /** Methodology pattern label (e.g. `six_layer_coherence`). */
  methodology: string | null;
  /** Topic hint for downstream filtering / chips, when present. */
  topicHint: string | null;
  /** Public publishedAt for conclusions / articles, generatedAt for
   *  opinions, createdAt for open questions. */
  occurredAt: string;
  /** Freshness signal: false once the item is past the staleness
   *  window. Stale results are still returned — readers see the pill,
   *  the result is never silently de-ranked. */
  isCurrent: boolean;
};

export type PublicAskResponse = {
  query: string;
  /** Query-understanding verdict — drives the per-class rendering
   *  path in `PublicAskBox`. */
  queryClass: PublicAskQueryClass;
  results: {
    conclusion: PublicAskResult[];
    opinion: PublicAskResult[];
    article: PublicAskResult[];
    open_question: PublicAskResult[];
  };
  topScore: number;
  noResult: boolean;
  closestOpenQuestion: PublicAskResult | null;
  /** Enriched no-result pointer: the closest related conclusion, so
   *  the "not addressed directly" page is a useful page, not a dead
   *  end. Present regardless of the threshold. */
  closestRelatedConclusion: PublicAskResult | null;
  suggestedRephrasings: string[];
  /** Coarse bucket id of the query — never the raw query. Logged at
   *  most for abuse aggregation. */
  queryBucket: string;
};

// ── Tokenisation ───────────────────────────────────────────────────────────

const TOKEN_RE = /[A-Za-z0-9]+/g;

const STOPWORDS = new Set([
  "a", "an", "and", "are", "as", "at", "be", "but", "by", "do", "does", "for",
  "from", "has", "have", "he", "her", "him", "his", "how", "i", "if", "in",
  "into", "is", "it", "its", "me", "my", "no", "not", "of", "on", "or", "our",
  "out", "said", "she", "so", "some", "such", "than", "that", "the", "their",
  "them", "they", "this", "to", "was", "we", "were", "what", "when", "where",
  "which", "who", "whom", "why", "will", "with", "you", "your",
]);

function tokenize(text: string): string[] {
  if (!text) return [];
  const toks: string[] = [];
  for (const match of text.toLowerCase().matchAll(TOKEN_RE)) {
    const tok = match[0];
    if (tok.length < 2) continue;
    if (STOPWORDS.has(tok)) continue;
    toks.push(tok);
  }
  return toks;
}

function uniq<T>(xs: Iterable<T>): T[] {
  return Array.from(new Set(xs));
}

// ── Snippet extraction ─────────────────────────────────────────────────────

const SENTENCE_RE = /(?<=[.!?])\s+(?=[A-Z0-9])/;

/**
 * Pick the highest-overlap sentence (and a small amount of trailing
 * context) from `text`. Strictly extractive — every character returned
 * appears in the source.
 */
export function extractSnippet(
  text: string,
  queryTokens: Set<string>,
  maxChars: number = SNIPPET_CHARS,
): string {
  const cleaned = (text ?? "").replace(/\s+/g, " ").trim();
  if (!cleaned) return "";
  if (cleaned.length <= maxChars) return cleaned;

  const sentences = cleaned.split(SENTENCE_RE).map((s) => s.trim()).filter(Boolean);
  if (sentences.length === 0) return cleaned.slice(0, maxChars).trimEnd() + "…";

  let bestIdx = 0;
  let bestScore = -1;
  for (let i = 0; i < sentences.length; i += 1) {
    const sentToks = tokenize(sentences[i]);
    let hits = 0;
    for (const t of sentToks) if (queryTokens.has(t)) hits += 1;
    if (hits > bestScore) {
      bestScore = hits;
      bestIdx = i;
    }
  }

  let chosen = sentences[bestIdx];
  let j = bestIdx + 1;
  while (j < sentences.length && chosen.length + 1 + sentences[j].length <= maxChars) {
    chosen = `${chosen} ${sentences[j]}`;
    j += 1;
  }
  if (chosen.length > maxChars) {
    chosen = `${chosen.slice(0, maxChars).trimEnd()}…`;
  }
  return chosen;
}

// ── Logging bucket ─────────────────────────────────────────────────────────

const BUCKET_SALT = "theseus-public-ask";

/**
 * Bucket id for a query. Anonymous public surface, so we never log the
 * raw query (a future reader could reconstruct what others asked). If
 * we log at all, this short hex prefix is the most we keep — useful for
 * coarse abuse aggregation, useless for reconstruction.
 */
export function hashQueryBucket(query: string): string {
  const norm = (query ?? "").toLowerCase().replace(/\s+/g, " ").trim();
  return createHash("sha256").update(`${BUCKET_SALT}|${norm}`).digest("hex").slice(0, 12);
}

// ── Query understanding (rule-based classifier) ────────────────────────────

/**
 * Rule layer for query classification. Mirrors the regex signals in
 * `noosphere/inference/query_classifier.py`. The live route runs this
 * layer only — it is cheap, deterministic, and within the 1.5s p50
 * budget. The Python module carries the optional light LLM judge for
 * the offline/Currents path; the route never freeform-generates.
 */
const CLASS_RULES: Array<{
  cls: PublicAskQueryClass;
  patterns: Array<{ name: string; re: RegExp; weight: number }>;
}> = [
  {
    cls: "methodology-question",
    patterns: [
      { name: "how-do-you", re: /\bhow (do|did|does|was|were|are) (you|the firm|theseus|this|it|they)\b/i, weight: 1.4 },
      { name: "methodology-word", re: /\bmethodolog/i, weight: 1.6 },
      { name: "derive", re: /\bhow .{0,40}\b(derive[ds]?|determine[ds]?|conclude[ds]?|reach(ed)?|arrive[ds]?|comput)/i, weight: 1.5 },
      { name: "process", re: /\bwhat(?:'s| is| are)? (?:your|the firm'?s?) (process|method|approach|reasoning|criteria)\b/i, weight: 1.5 },
      { name: "how-know", re: /\bhow (do|did) (you|the firm) know\b/i, weight: 1.4 },
      { name: "firm-method-terms", re: /\b(six.?layer|coherence layer|provenance|audit trail|show your work)\b/i, weight: 1.3 },
      { name: "on-what-basis", re: /\b(on what basis|what evidence|what makes you (so )?(sure|confident))\b/i, weight: 1.2 },
    ],
  },
  {
    cls: "prediction-request",
    patterns: [
      { name: "will", re: /\bwill\b/i, weight: 1.0 },
      { name: "forecast-word", re: /\b(predict|forecast|projection|outlook|prognos)/i, weight: 1.6 },
      { name: "going-to", re: /\b(going to|expected to|likely to|on track to)\b/i, weight: 1.1 },
      { name: "by-year", re: /\bby (?:the )?(?:end of )?(?:19|20)\d\d\b/i, weight: 1.5 },
      { name: "in-coming", re: /\bin (?:the )?(?:next|coming) \d*\s*(year|month|decade|quarter)/i, weight: 1.4 },
      { name: "what-happens-if", re: /\bwhat (?:will|would) happen (?:if|when)\b/i, weight: 1.3 },
      { name: "future-of", re: /\bfuture of\b/i, weight: 1.0 },
    ],
  },
  {
    cls: "counter-argument-request",
    patterns: [
      { name: "counter-word", re: /\bcounter.?(argument|point|case)/i, weight: 1.7 },
      { name: "against", re: /\b(argue|argument|case|evidence) against\b/i, weight: 1.6 },
      { name: "steelman", re: /\b(steel.?man|devil'?s advocate)\b/i, weight: 1.8 },
      { name: "rebut", re: /\b(rebut|refut|disprove|debunk)/i, weight: 1.5 },
      { name: "objection", re: /\bobjection/i, weight: 1.3 },
      { name: "might-be-wrong", re: /\b(why|where|how) (might|would|could|is|are) .{0,40}\b(wrong|mistaken|flawed|fail)/i, weight: 1.5 },
      { name: "strongest-against", re: /\bstrongest (argument|case|objection)\b/i, weight: 1.6 },
      { name: "disagree", re: /\b(disagree|pushback|push back|critique of|weakest)\b/i, weight: 1.1 },
      { name: "contradict", re: /\bcontradict/i, weight: 1.2 },
    ],
  },
  {
    cls: "factual-claim",
    patterns: [
      { name: "what-firm-thinks", re: /\bwhat (?:does|do) the firm (?:think|believe|conclude|say|hold)\b/i, weight: 1.6 },
      { name: "firm-view-on", re: /\b(?:the firm'?s?|your) (view|position|conclusion|take|stance) on\b/i, weight: 1.5 },
      { name: "is-it-true", re: /\bis it true\b/i, weight: 1.4 },
      { name: "interrogative-fact", re: /^(is|are|does|do|did|has|have|was|were|can|should|which)\b.*\?$/i, weight: 1.0 },
      { name: "what-is", re: /\bwhat (?:is|are)\b/i, weight: 0.8 },
      { name: "declarative", re: /^[a-z0-9].{0,200}\b(is|are|was|were|drives?|causes?|funds?|leads? to)\b.{0,200}[^?]$/i, weight: 0.7 },
    ],
  },
];

const VERBISH =
  /\b(is|are|was|were|do|does|did|will|would|should|can|how|why|what|when|where|which|who|predict|argue|think|believe)\b/i;

/** A bare topic is a short noun-phrase query: browse intent. */
function isBareTopic(query: string): boolean {
  const q = query.trim();
  if (!q || q.includes("?")) return false;
  if (VERBISH.test(q)) return false;
  return q.split(/\s+/).length <= 6;
}

/**
 * Classify a query into one of the five `PublicAskQueryClass` values.
 * Highest summed rule weight wins; with no class-specific signal a bare
 * topic is `browse` and anything else falls back to `browse` too (the
 * route has no LLM judge to break the tie).
 */
export function classifyQuery(query: string): PublicAskQueryClass {
  const q = (query ?? "").trim();
  if (!q) return "browse";

  let bestClass: PublicAskQueryClass = "browse";
  let bestScore = 0;
  for (const { cls, patterns } of CLASS_RULES) {
    let score = 0;
    for (const { re, weight } of patterns) {
      if (re.test(q)) score += weight;
    }
    if (score > bestScore) {
      bestScore = score;
      bestClass = cls;
    }
  }
  if (bestScore <= 0) return "browse";
  return bestClass;
}

/**
 * Per-class retrieval profile. `kindBoost` re-weights rails for
 * *ordering and diversity selection only* — never the no-result
 * threshold, so honesty about silence stays calibrated. `mmrLambda`
 * tunes the relevance/diversity tradeoff: a counter-argument query
 * runs a low λ to surface the spread of disagreement rather than the
 * loudest echo. Mirrors `RetrievalProfile` in the Python module.
 */
type ClassProfile = {
  kindBoost: Partial<Record<PublicAskKind, number>>;
  mmrLambda: number;
};

const CLASS_PROFILES: Record<PublicAskQueryClass, ClassProfile> = {
  "factual-claim": {
    kindBoost: { conclusion: 1.5, article: 1.15 },
    mmrLambda: 0.78,
  },
  "methodology-question": {
    kindBoost: { article: 1.5, open_question: 1.25, conclusion: 1.1 },
    mmrLambda: 0.62,
  },
  "prediction-request": {
    kindBoost: { opinion: 1.5, open_question: 1.15 },
    mmrLambda: 0.58,
  },
  "counter-argument-request": {
    kindBoost: { open_question: 1.6, opinion: 1.2 },
    mmrLambda: 0.4,
  },
  // Neutral — browse keeps the original relevance ordering.
  browse: { kindBoost: {}, mmrLambda: MMR_LAMBDA_DEFAULT },
};

// ── Maximum Marginal Relevance ─────────────────────────────────────────────

/**
 * Cosine similarity between two sparse token-weight vectors. Used by
 * MMR to measure item-to-item redundancy.
 */
function sparseCosine(a: Map<string, number>, b: Map<string, number>): number {
  const [small, large] = a.size <= b.size ? [a, b] : [b, a];
  let dot = 0;
  for (const [k, v] of small) {
    const w = large.get(k);
    if (w) dot += v * w;
  }
  let na = 0;
  for (const v of a.values()) na += v * v;
  let nb = 0;
  for (const v of b.values()) nb += v * v;
  if (na < 1e-12 || nb < 1e-12) return 0;
  return dot / Math.sqrt(na * nb);
}

type MmrCandidate = {
  item: CorpusItem;
  /** Raw relevance score (boost-adjusted for ordering). */
  relevance: number;
  /** IDF-weighted token vector for redundancy measurement. */
  vec: Map<string, number>;
};

/**
 * Maximum Marginal Relevance selection. Greedily picks `k` items, each
 * step maximising `λ · relevance − (1 − λ) · max-similarity-to-picked`.
 * The first pick is always the most relevant item, so relevance-ordered
 * behaviour is preserved at the top; subsequent picks trade relevance
 * against not being near-duplicates of what is already shown.
 */
export function mmrSelect(
  candidates: MmrCandidate[],
  lambda: number,
  k: number,
): MmrCandidate[] {
  if (k <= 0 || candidates.length === 0) return [];
  const lam = Math.max(0, Math.min(1, lambda));
  const maxRel = candidates.reduce((m, c) => Math.max(m, c.relevance), 0);
  const norm = maxRel > 1e-12 ? maxRel : 1;

  const remaining = [...candidates];
  const selected: MmrCandidate[] = [];
  while (remaining.length > 0 && selected.length < k) {
    let bestIdx = 0;
    let bestVal = -Infinity;
    for (let i = 0; i < remaining.length; i += 1) {
      const cand = remaining[i];
      const rel = cand.relevance / norm;
      let penalty = 0;
      for (const s of selected) {
        const sim = sparseCosine(cand.vec, s.vec);
        if (sim > penalty) penalty = sim;
      }
      const val = lam * rel - (1 - lam) * penalty;
      if (val > bestVal) {
        bestVal = val;
        bestIdx = i;
      }
    }
    selected.push(remaining.splice(bestIdx, 1)[0]);
  }
  return selected;
}

// ── Freshness ──────────────────────────────────────────────────────────────

/**
 * Whether an item is "still considered current". Date-driven: an item
 * older than the staleness window is stale. An unparseable / missing
 * date is treated as current — we never fabricate a stale signal we
 * cannot back with a date.
 */
function computeIsCurrent(occurredAt: string, now: number): boolean {
  const ts = Date.parse(occurredAt);
  if (Number.isNaN(ts)) return true;
  const ageDays = (now - ts) / 86_400_000;
  return ageDays < FRESHNESS_STALE_DAYS;
}

// ── Internal corpus shape ──────────────────────────────────────────────────

type CorpusItem = {
  id: string;
  kind: PublicAskKind;
  title: string;
  text: string;
  href: string;
  confidence: number | null;
  methodology: string | null;
  topicHint: string | null;
  occurredAt: string;
};

// ── Loaders ────────────────────────────────────────────────────────────────

const PUBLIC_LOAD_CAP = 200;

function plain(text: string): string {
  return (text ?? "").replace(/\s+/g, " ").trim();
}

function methodologyOf(payloadJson: string): string | null {
  try {
    const parsed = JSON.parse(payloadJson) as Record<string, unknown>;
    const methodology = parsed?.methodology as Record<string, unknown> | undefined;
    const profiles = methodology?.profiles as Array<Record<string, unknown>> | undefined;
    const first = profiles && profiles.length > 0 ? profiles[0] : null;
    const patternType = first?.patternType;
    if (typeof patternType === "string" && patternType.trim()) return patternType.trim();
  } catch {
    // ignore — payload is occasionally legacy
  }
  return null;
}

function bodyOf(payloadJson: string): { conclusionText: string; rationale: string; article: string; topicHint: string } {
  try {
    const parsed = JSON.parse(payloadJson) as Record<string, unknown>;
    const article = parsed?.article as Record<string, unknown> | undefined;
    return {
      conclusionText: typeof parsed?.conclusionText === "string" ? parsed.conclusionText : "",
      rationale: typeof parsed?.rationale === "string" ? parsed.rationale : "",
      article: typeof article?.bodyMarkdown === "string" ? article.bodyMarkdown : "",
      topicHint: typeof parsed?.topicHint === "string" ? parsed.topicHint : "",
    };
  } catch {
    return { conclusionText: "", rationale: "", article: "", topicHint: "" };
  }
}

async function loadPublishedCorpus(organizationId: string): Promise<CorpusItem[]> {
  const rows = await db.publishedConclusion.findMany({
    where: { organizationId },
    orderBy: { publishedAt: "desc" },
    take: PUBLIC_LOAD_CAP,
    select: {
      id: true,
      slug: true,
      version: true,
      kind: true,
      payloadJson: true,
      publishedAt: true,
      statedConfidence: true,
      discountedConfidence: true,
    },
  });
  return rows.map((row) => {
    const body = bodyOf(row.payloadJson);
    const isArticle = (row.kind ?? "CONCLUSION") === "ARTICLE";
    const text = [body.conclusionText, body.rationale, body.article].filter(Boolean).join(" \n\n ");
    return {
      id: row.id,
      kind: isArticle ? ("article" as const) : ("conclusion" as const),
      title: body.conclusionText || row.slug,
      text: plain(text) || body.conclusionText || row.slug,
      href: `/c/${encodeURIComponent(row.slug)}`,
      confidence: typeof row.discountedConfidence === "number" ? row.discountedConfidence : row.statedConfidence,
      methodology: methodologyOf(row.payloadJson),
      topicHint: body.topicHint || null,
      occurredAt: row.publishedAt instanceof Date ? row.publishedAt.toISOString() : new Date(row.publishedAt).toISOString(),
    };
  });
}

async function loadOpinionCorpus(organizationId: string): Promise<CorpusItem[]> {
  const rows = await db.eventOpinion.findMany({
    where: {
      organizationId,
      revokedAt: null,
      abstentionReason: null,
    },
    orderBy: { generatedAt: "desc" },
    take: PUBLIC_LOAD_CAP,
    select: {
      id: true,
      headline: true,
      bodyMarkdown: true,
      topicHint: true,
      confidence: true,
      generatedAt: true,
    },
  });
  return rows.map((row) => ({
    id: row.id,
    kind: "opinion" as const,
    title: row.headline,
    text: plain(`${row.headline}. ${row.bodyMarkdown ?? ""}`),
    href: `/currents/${encodeURIComponent(row.id)}`,
    confidence: typeof row.confidence === "number" ? row.confidence : null,
    methodology: "currents",
    topicHint: row.topicHint || null,
    occurredAt: row.generatedAt instanceof Date ? row.generatedAt.toISOString() : new Date(row.generatedAt).toISOString(),
  }));
}

async function loadOpenQuestionCorpus(organizationId: string): Promise<CorpusItem[]> {
  const rows = await loadPublicOpenQuestions(organizationId, { limit: PUBLIC_LOAD_CAP });
  return rows.map((row) => ({
    id: row.id,
    kind: "open_question" as const,
    title: row.summary,
    text: row.summary,
    href: `/methodology/open-questions#q-${encodeURIComponent(row.id)}`,
    confidence: null,
    methodology: row.candidateMethodNames[0] ?? null,
    topicHint: row.domain || null,
    occurredAt: row.createdAt instanceof Date ? row.createdAt.toISOString() : new Date(row.createdAt).toISOString(),
  }));
}

// ── Scoring ────────────────────────────────────────────────────────────────

function buildIdf(corpus: CorpusItem[]): Map<string, number> {
  const df = new Map<string, number>();
  for (const item of corpus) {
    for (const tok of uniq(tokenize(`${item.title} ${item.text}`))) {
      df.set(tok, (df.get(tok) ?? 0) + 1);
    }
  }
  const N = corpus.length || 1;
  const idf = new Map<string, number>();
  for (const [tok, count] of df) {
    idf.set(tok, Math.log(1 + N / count));
  }
  return idf;
}

function scoreItem(
  queryTokens: string[],
  item: CorpusItem,
  idf: Map<string, number>,
): number {
  if (queryTokens.length === 0) return 0;
  const titleSet = new Set(tokenize(item.title));
  const docCounts = new Map<string, number>();
  for (const t of tokenize(item.text)) {
    docCounts.set(t, (docCounts.get(t) ?? 0) + 1);
  }
  let score = 0;
  let qWeight = 0;
  for (const qt of queryTokens) {
    const w = idf.get(qt) ?? Math.log(1 + 100); // out-of-corpus tokens still weighed
    qWeight += w;
    const hits = docCounts.get(qt) ?? 0;
    if (hits === 0 && !titleSet.has(qt)) continue;
    let contribution = w * Math.log(1 + hits);
    if (titleSet.has(qt)) contribution += w * Math.log(1 + 1) * TITLE_BOOST;
    score += contribution;
  }
  if (qWeight === 0) return 0;
  // Normalise so threshold logic is comparable across queries.
  const docMass = Math.log(1 + Math.max(item.text.length / 80, 4));
  return score / (qWeight * docMass);
}

// ── Public entrypoint ──────────────────────────────────────────────────────

export type LoadCorpus = (organizationId: string) => Promise<CorpusItem[]>;

export async function buildPublicCorpus(organizationId: string): Promise<CorpusItem[]> {
  const [conclusions, opinions, openQs] = await Promise.all([
    loadPublishedCorpus(organizationId),
    loadOpinionCorpus(organizationId),
    loadOpenQuestionCorpus(organizationId),
  ]);
  return [...conclusions, ...opinions, ...openQs];
}

function emptyResponse(query: string, queryBucket: string): PublicAskResponse {
  return {
    query,
    queryClass: classifyQuery(query),
    results: {
      conclusion: [],
      opinion: [],
      article: [],
      open_question: [],
    },
    topScore: 0,
    noResult: true,
    closestOpenQuestion: null,
    closestRelatedConclusion: null,
    suggestedRephrasings: [],
    queryBucket,
  };
}

export async function publicAsk(
  rawQuery: string,
  options: { corpus?: CorpusItem[] } = {},
): Promise<PublicAskResponse> {
  const query = (rawQuery ?? "").slice(0, MAX_QUERY_LEN).trim();
  const queryBucket = hashQueryBucket(query);

  if (query.length < MIN_QUERY_LEN) {
    return emptyResponse(query, queryBucket);
  }

  const queryTokens = tokenize(query);
  if (queryTokens.length === 0) {
    return emptyResponse(query, queryBucket);
  }

  let corpus = options.corpus;
  if (!corpus) {
    const orgId = await resolvePublicOrganizationId();
    if (!orgId) return emptyResponse(query, queryBucket);
    corpus = await buildPublicCorpus(orgId);
  }
  if (corpus.length === 0) return emptyResponse(query, queryBucket);

  return rankAndShape(query, queryTokens, corpus, queryBucket);
}

/** IDF-weighted token vector for an item — MMR's redundancy metric. */
function itemVector(item: CorpusItem, idf: Map<string, number>): Map<string, number> {
  const vec = new Map<string, number>();
  for (const tok of tokenize(`${item.title} ${item.text}`)) {
    const w = idf.get(tok) ?? Math.log(1 + 100);
    vec.set(tok, (vec.get(tok) ?? 0) + w);
  }
  return vec;
}

function rankAndShape(
  query: string,
  queryTokens: string[],
  corpus: CorpusItem[],
  queryBucket: string,
): PublicAskResponse {
  const idf = buildIdf(corpus);
  const querySet = new Set(queryTokens);
  const now = Date.now();

  // Query understanding: route the query into a class, pick its
  // retrieval profile. The route runs the rule layer only.
  const queryClass = classifyQuery(query);
  const profile = CLASS_PROFILES[queryClass];

  const scored = corpus
    .map((item) => ({ item, score: scoreItem(queryTokens, item, idf) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score);

  const toResult = (item: CorpusItem, score: number): PublicAskResult => ({
    id: item.id,
    kind: item.kind,
    title: item.title,
    href: item.href,
    snippet: extractSnippet(item.text, querySet),
    relevance: clip01(score),
    confidence: item.confidence,
    methodology: item.methodology,
    topicHint: item.topicHint,
    occurredAt: item.occurredAt,
    isCurrent: computeIsCurrent(item.occurredAt, now),
  });

  // Per-rail diversity: gather each kind's scored items, apply the
  // class's per-kind boost for ordering, and run MMR so a rail is not
  // five paraphrases of one conclusion. The boost touches ordering
  // only — the no-result threshold below still reads the raw score.
  const buckets: PublicAskResponse["results"] = {
    conclusion: [],
    opinion: [],
    article: [],
    open_question: [],
  };
  const rawScoreById = new Map<string, number>();
  const candidatesByKind: Record<PublicAskKind, MmrCandidate[]> = {
    conclusion: [],
    opinion: [],
    article: [],
    open_question: [],
  };
  for (const { item, score } of scored) {
    rawScoreById.set(item.id, score);
    const boost = profile.kindBoost[item.kind] ?? 1;
    candidatesByKind[item.kind].push({
      item,
      relevance: score * boost,
      vec: itemVector(item, idf),
    });
  }
  for (const kind of Object.keys(buckets) as PublicAskKind[]) {
    const picked = mmrSelect(candidatesByKind[kind], profile.mmrLambda, TOP_PER_KIND);
    for (const cand of picked) {
      buckets[kind].push(toResult(cand.item, rawScoreById.get(cand.item.id) ?? 0));
    }
  }

  const topScore = scored.length > 0 ? scored[0].score : 0;
  const noResult = topScore < NO_RESULT_THRESHOLD;

  // Closest pointers for the (enriched) no-result panel: the best
  // open question AND the best related conclusion, surfaced regardless
  // of the threshold so "not addressed directly" is still a useful
  // page. Each falls through to *any* item of its kind so a reader on
  // a true no-result query is never left with a dead end.
  const firstOfKind = (kind: PublicAskKind): PublicAskResult | null => {
    for (const { item, score } of scored) {
      if (item.kind === kind) return toResult(item, score);
    }
    const any = corpus.find((item) => item.kind === kind);
    return any ? toResult(any, 0) : null;
  };
  const closestOpenQuestion = firstOfKind("open_question");
  const closestRelatedConclusion = firstOfKind("conclusion");

  const suggestedRephrasings: string[] = [];
  if (
    scored.length > 0 &&
    topScore >= BORDERLINE_LOWER &&
    topScore < BORDERLINE_UPPER
  ) {
    const seen = new Set([scored[0].item.id]);
    for (const { item } of scored.slice(1)) {
      if (seen.has(item.id)) continue;
      seen.add(item.id);
      suggestedRephrasings.push(item.title);
      if (suggestedRephrasings.length >= 3) break;
    }
  }

  return {
    query,
    queryClass,
    results: buckets,
    topScore: clip01(topScore),
    noResult,
    closestOpenQuestion,
    closestRelatedConclusion,
    suggestedRephrasings,
    queryBucket,
  };
}

function clip01(x: number): number {
  if (!Number.isFinite(x)) return 0;
  if (x < 0) return 0;
  if (x > 1) return 1;
  return x;
}

// ── Research suggestion submission ─────────────────────────────────────────

export type ResearchSuggestionInput = {
  title: string;
  summary?: string;
  rationale?: string;
};

export type ResearchSuggestionResult = { id: string };

const SUGGESTION_TITLE_MIN = 8;
const SUGGESTION_TITLE_MAX = 240;
const SUGGESTION_FIELD_MAX = 2_000;

/**
 * Persist a reader-submitted research suggestion from the enriched
 * no-result panel — the "the firm has not addressed this directly"
 * branch becomes a place a reader can act rather than a dead end.
 *
 * This is the one *write* on the public ask surface. It is not
 * generation: it stores exactly what the reader typed into the form.
 * The originating search query is deliberately NOT attached — query-log
 * discipline keeps raw query strings out of long-lived rows (see
 * `hashQueryBucket` and the retention runner). Mirrors
 * `noosphere.models.ResearchSuggestion`.
 */
export async function submitPublicResearchSuggestion(
  input: ResearchSuggestionInput,
): Promise<ResearchSuggestionResult> {
  const title = (input?.title ?? "").trim().slice(0, SUGGESTION_TITLE_MAX);
  if (title.length < SUGGESTION_TITLE_MIN) {
    throw new Error("Suggestion needs a title of at least 8 characters");
  }
  const summary = (input?.summary ?? "").trim().slice(0, SUGGESTION_FIELD_MAX);
  const rationale = (input?.rationale ?? "").trim().slice(0, SUGGESTION_FIELD_MAX);

  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) {
    throw new Error("No public organization configured");
  }

  const row = await db.researchSuggestion.create({
    data: {
      organizationId,
      title,
      summary,
      rationale,
      sessionLabel: "public-ask",
    },
    select: { id: true },
  });
  return { id: row.id };
}

// ── Rate limit ─────────────────────────────────────────────────────────────

type Bucket = { count: number; resetAt: number };
const askBuckets = new Map<string, Bucket>();

const RATE_WINDOW_MS = 60 * 1000;
const RATE_MAX = 30;

/**
 * Fixed-window per-IP limiter. Anonymous public endpoint, so the only
 * key we have is the request IP. In-memory — fine for a single
 * Next.js worker; a multi-instance prod deployment should swap this
 * for the same Redis-backed limiter Currents uses.
 */
export function checkPublicAskRateLimit(
  ipKey: string,
  now: number = Date.now(),
): { ok: true } | { ok: false; retryAfterSec: number } {
  let bucket = askBuckets.get(ipKey);
  if (!bucket || now > bucket.resetAt) {
    bucket = { count: 0, resetAt: now + RATE_WINDOW_MS };
    askBuckets.set(ipKey, bucket);
  }
  if (bucket.count >= RATE_MAX) {
    const retryAfterSec = Math.max(1, Math.ceil((bucket.resetAt - now) / 1000));
    return { ok: false, retryAfterSec };
  }
  bucket.count += 1;
  return { ok: true };
}

export function _resetPublicAskRateLimitsForTests(): void {
  askBuckets.clear();
}
