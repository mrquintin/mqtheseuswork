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
 * and snippet-extraction contract so a future cutover to a Currents
 * embedding service is wire-level only.
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

// ── Public types ───────────────────────────────────────────────────────────

export type PublicAskKind = "conclusion" | "opinion" | "article" | "open_question";

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
};

export type PublicAskResponse = {
  query: string;
  results: {
    conclusion: PublicAskResult[];
    opinion: PublicAskResult[];
    article: PublicAskResult[];
    open_question: PublicAskResult[];
  };
  topScore: number;
  noResult: boolean;
  closestOpenQuestion: PublicAskResult | null;
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
    results: {
      conclusion: [],
      opinion: [],
      article: [],
      open_question: [],
    },
    topScore: 0,
    noResult: true,
    closestOpenQuestion: null,
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

function rankAndShape(
  query: string,
  queryTokens: string[],
  corpus: CorpusItem[],
  queryBucket: string,
): PublicAskResponse {
  const idf = buildIdf(corpus);
  const querySet = new Set(queryTokens);

  const scored = corpus
    .map((item) => ({ item, score: scoreItem(queryTokens, item, idf) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score);

  const buckets: PublicAskResponse["results"] = {
    conclusion: [],
    opinion: [],
    article: [],
    open_question: [],
  };

  for (const { item, score } of scored) {
    const bucket = buckets[item.kind];
    if (bucket.length >= TOP_PER_KIND) continue;
    bucket.push({
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
    });
  }

  const topScore = scored.length > 0 ? scored[0].score : 0;
  const noResult = topScore < NO_RESULT_THRESHOLD;

  let closestOpenQuestion: PublicAskResult | null = null;
  for (const { item, score } of scored) {
    if (item.kind !== "open_question") continue;
    closestOpenQuestion = {
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
    };
    break;
  }
  // If no open question scored above zero, still try to fall through to
  // the most recent one — a reader on a no-result query deserves a
  // pointer to *something* the firm has flagged as unresolved.
  if (!closestOpenQuestion) {
    const anyOpen = corpus.find((item) => item.kind === "open_question");
    if (anyOpen) {
      closestOpenQuestion = {
        id: anyOpen.id,
        kind: anyOpen.kind,
        title: anyOpen.title,
        href: anyOpen.href,
        snippet: extractSnippet(anyOpen.text, querySet),
        relevance: 0,
        confidence: anyOpen.confidence,
        methodology: anyOpen.methodology,
        topicHint: anyOpen.topicHint,
        occurredAt: anyOpen.occurredAt,
      };
    }
  }

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
    results: buckets,
    topScore: clip01(topScore),
    noResult,
    closestOpenQuestion,
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
