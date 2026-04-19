import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";
import { sanitizeAndCap } from "@/lib/sanitizeText";

/**
 * Ask the Codex — grounded RAG query surface.
 *
 * The central value proposition of the system: the founder asks a
 * question; the oracle answers using what the firm has uploaded,
 * citing specific sources. Previously this endpoint only had access
 * to `Conclusion` rows (atomic claims Noosphere has distilled from
 * uploads) and refused to answer if the firm hadn't recorded a
 * position. That made it feel brittle — a firm with 3 conclusions
 * couldn't ask anything beyond those 3 statements.
 *
 * Current behaviour:
 *
 *   1. Authenticate (cookie session OR Bearer API key).
 *   2. Gather ALL relevant corpus material for the caller's
 *      organisation:
 *        a. Conclusions — atomic claims, already distilled.
 *        b. Upload excerpts — raw text content, chunked + scored
 *           by keyword overlap with the question. This is the new
 *           "retrieval" half of RAG; previously absent.
 *   3. Send the corpus to Claude Opus 4.7 (configurable via
 *      ASK_LLM_MODEL) via the Anthropic REST API.
 *   4. ALWAYS produce an answer. If nothing in the corpus applies,
 *      Claude answers from general knowledge and flags the answer
 *      as un-sourced. This replaces the previous "the firm has not
 *      recorded a position" refusal pattern.
 *   5. Return the answer plus a structured `sources` list so the UI
 *      can render both Conclusion citations and Upload citations
 *      (with slug links where the upload is published).
 *
 * Why fetch() instead of @anthropic-ai/sdk
 * -----------------------------------------
 * Anthropic's /v1/messages endpoint is a trivial JSON POST. Pulling
 * in the SDK for a single call bloats the serverless bundle and
 * brings its own transitive deps; direct fetch is ~40 lines of glue
 * and has no version-drift risk.
 */

// ─── Model config ──────────────────────────────────────────────────

/** Default model. claude-opus-4-7 launched 16 Apr 2026 as Anthropic's
 *  flagship for complex reasoning. Override via ASK_LLM_MODEL if a
 *  newer Opus/Sonnet ships. */
const DEFAULT_MODEL = "claude-opus-4-7";
const ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages";
const ANTHROPIC_API_VERSION = "2023-06-01";

// ─── Retrieval tuning ──────────────────────────────────────────────

/** Max Conclusions loaded into context. They're already small (~200
 *  chars each) so we can fit them all up to this cap even on
 *  reasoning-heavy models. */
const MAX_CONCLUSIONS = 150;

/** Max upload rows to scan when building retrieval chunks. Ordered
 *  by createdAt desc — recent material is usually more relevant. */
const MAX_UPLOADS_TO_SCAN = 40;

/** Approximate characters per retrieved upload chunk. Paragraph-sized. */
const CHUNK_TARGET_CHARS = 800;

/** How many top-scoring upload chunks to include in the prompt.
 *  15 chunks × 800 chars ≈ 12k chars ≈ 3k tokens — well under any
 *  modern model's input budget. */
const TOP_CHUNKS = 15;

/** Lowercase English stopwords to filter out before scoring. Short
 *  list kept on purpose — we want ok recall, not NLP-grade filtering. */
const STOPWORDS = new Set([
  "a",
  "an",
  "and",
  "are",
  "as",
  "at",
  "be",
  "but",
  "by",
  "do",
  "does",
  "for",
  "from",
  "has",
  "have",
  "he",
  "her",
  "him",
  "his",
  "how",
  "i",
  "if",
  "in",
  "into",
  "is",
  "it",
  "its",
  "me",
  "my",
  "no",
  "not",
  "of",
  "on",
  "or",
  "our",
  "out",
  "said",
  "she",
  "so",
  "that",
  "the",
  "their",
  "them",
  "then",
  "there",
  "they",
  "this",
  "to",
  "was",
  "we",
  "were",
  "what",
  "when",
  "where",
  "which",
  "who",
  "why",
  "will",
  "with",
  "would",
  "you",
  "your",
]);

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((t) => t.length >= 3 && !STOPWORDS.has(t));
}

interface ChunkRecord {
  uploadId: string;
  uploadTitle: string;
  uploadSlug: string | null;
  chunkIndex: number;
  text: string;
  score: number;
}

/**
 * Split a long text into ~CHUNK_TARGET_CHARS-sized chunks on
 * paragraph or sentence boundaries. Keeps reasonable semantic
 * coherence without a real tokenizer.
 */
function chunkText(text: string): string[] {
  if (!text) return [];
  // Split on paragraph breaks first.
  const paras = text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  const chunks: string[] = [];
  let buf = "";
  for (const p of paras) {
    if (!buf) {
      buf = p;
    } else if ((buf + "\n\n" + p).length <= CHUNK_TARGET_CHARS * 1.5) {
      buf += "\n\n" + p;
    } else {
      chunks.push(buf);
      buf = p;
    }
    if (buf.length >= CHUNK_TARGET_CHARS) {
      chunks.push(buf);
      buf = "";
    }
  }
  if (buf) chunks.push(buf);

  // Further split any still-oversized chunks on sentence boundaries.
  const out: string[] = [];
  for (const c of chunks) {
    if (c.length <= CHUNK_TARGET_CHARS * 1.8) {
      out.push(c);
      continue;
    }
    const sentences = c.split(/(?<=[.!?])\s+(?=[A-Z])/);
    let s = "";
    for (const sent of sentences) {
      if (!s) {
        s = sent;
      } else if ((s + " " + sent).length <= CHUNK_TARGET_CHARS) {
        s += " " + sent;
      } else {
        out.push(s);
        s = sent;
      }
    }
    if (s) out.push(s);
  }
  return out;
}

/**
 * Score a chunk for relevance: count how many UNIQUE question tokens
 * appear in the chunk, normalised by sqrt(chunk length) so longer
 * chunks don't dominate just by being longer. This is a poor-man's
 * TF-IDF — good enough for ~hundreds of chunks without embedding
 * infrastructure.
 */
function scoreChunk(chunk: string, questionTokens: Set<string>): number {
  if (questionTokens.size === 0) return 0;
  const chunkTokens = new Set(tokenize(chunk));
  let matches = 0;
  for (const t of questionTokens) {
    if (chunkTokens.has(t)) matches++;
  }
  if (matches === 0) return 0;
  // sqrt(length) normalisation: modestly prefer shorter chunks with
  // the same match count, without heavily penalising long chunks.
  return matches / Math.max(1, Math.sqrt(chunk.length / 100));
}

// ─── Prompt assembly ───────────────────────────────────────────────

const SYSTEM_PROMPT = `You are the oracle of the Theseus Codex — a firm's institutional memory surface.

Your job: answer the founder's question. You have two kinds of source material to draw on, in order of priority:

1. FIRM CONCLUSIONS — atomic claims the firm has distilled from its work and recorded. Each carries a confidenceTier:
     firm     — the firm stands behind this belief in its strongest form.
     founder  — a single founder's conviction; not yet firm-wide.
     open     — an unresolved coherence tension, under active review.
     retired  — a belief the firm formerly held, now retracted.

2. UPLOAD EXCERPTS — passages from sessions, transcripts, essays, and papers the firm has uploaded. Retrieved for relevance to the question.

Citation protocol (IMPORTANT):

  When you make a claim grounded in a firm Conclusion, cite it inline using [C:<first-8-chars-of-id>]. Example: "Position sizing is bounded by conviction half-life [C:cmo4sd12]."
  When you make a claim grounded in an Upload excerpt, cite it using [U:<short-title>]. Example: "[U:Q3 retro] suggests the opposite."
  Multiple citations on the same sentence are fine: "... [C:cmo4sd12] [U:Q3 retro]."

Answering rules:

  ALWAYS answer the question. Do not refuse or say "the firm has not recorded a position."

  If the firm's corpus has directly relevant material, answer primarily from it and cite heavily.

  If the corpus only partially addresses the question, answer the covered parts from the corpus (with citations) and the uncovered parts from your own general knowledge (without citations), being explicit about the boundary. Example: "On the first half the firm has recorded [C:...]. On the second half the firm has no recorded position; from general knowledge, ..."

  If the corpus does not address the question at all, answer from your own general knowledge and open with a brief disclaimer: "The firm has not recorded material on this; from general knowledge:".

  Never cite retired tier as current belief.

  Weight firm and founder tiers heavily; treat open as unresolved.

  Prefer concision. One to three sentences is ideal. Longer only when the question genuinely demands it.`;

interface ConclusionContext {
  id: string;
  text: string;
  confidenceTier: string;
  topicHint: string;
  rationale: string;
}

interface UploadContext {
  id: string;
  title: string;
  slug: string | null;
}

function buildUserMessage(
  question: string,
  conclusions: ConclusionContext[],
  chunks: ChunkRecord[],
): string {
  const parts: string[] = [];

  if (conclusions.length > 0) {
    const rendered = conclusions
      .map(
        (c) =>
          `- [C:${c.id.slice(0, 8)}] tier=${c.confidenceTier} · topic=${
            c.topicHint || "general"
          }\n  ${c.text}${c.rationale ? `\n  (rationale: ${c.rationale.slice(0, 300)})` : ""}`,
      )
      .join("\n");
    parts.push(`FIRM CONCLUSIONS (${conclusions.length}):\n${rendered}`);
  } else {
    parts.push("FIRM CONCLUSIONS: (none recorded yet)");
  }

  if (chunks.length > 0) {
    const rendered = chunks
      .map(
        (c) =>
          `— [U:${c.uploadTitle.slice(0, 40)}]${c.uploadSlug ? ` (/post/${c.uploadSlug})` : ""}\n${c.text}`,
      )
      .join("\n\n");
    parts.push(
      `UPLOAD EXCERPTS (top ${chunks.length} by relevance to this question):\n${rendered}`,
    );
  } else {
    parts.push(
      "UPLOAD EXCERPTS: (no relevant passages found in the firm's uploads)",
    );
  }

  parts.push(`———\n\nQuestion: ${question}`);
  return parts.join("\n\n");
}

// ─── Anthropic call ────────────────────────────────────────────────

interface AnthropicContentBlock {
  type: string;
  text?: string;
}

interface AnthropicResponse {
  content?: AnthropicContentBlock[];
  stop_reason?: string;
  usage?: { input_tokens?: number; output_tokens?: number };
  model?: string;
  error?: { type?: string; message?: string };
}

async function callClaude(
  apiKey: string,
  model: string,
  userMessage: string,
): Promise<{ text: string; inputTokens: number; outputTokens: number }> {
  const res = await fetch(ANTHROPIC_MESSAGES_URL, {
    method: "POST",
    headers: {
      "x-api-key": apiKey,
      "anthropic-version": ANTHROPIC_API_VERSION,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model,
      max_tokens: 1024,
      // `temperature` was explicitly omitted: Anthropic deprecated
      // it for claude-opus-4-7 (POST returns
      // `invalid_request_error: temperature is deprecated for this
      // model.` if you pass any value). Opus 4.7 uses its own
      // internal reasoning schedule; the grounded-system-prompt +
      // retrieved-context pattern produces appropriately terse,
      // citation-heavy answers on its own.
      system: SYSTEM_PROMPT,
      messages: [{ role: "user", content: userMessage }],
    }),
  });

  const bodyText = await res.text();
  let parsed: AnthropicResponse;
  try {
    parsed = JSON.parse(bodyText) as AnthropicResponse;
  } catch {
    throw new Error(
      `Anthropic returned non-JSON response (HTTP ${res.status}): ${bodyText.slice(0, 240)}`,
    );
  }

  if (!res.ok) {
    const msg = parsed.error?.message || `HTTP ${res.status}`;
    throw new Error(`Anthropic ${parsed.error?.type || "error"}: ${msg}`);
  }

  const textBlock = parsed.content?.find((b) => b.type === "text");
  const text = (textBlock?.text || "").trim();
  if (!text) {
    throw new Error("Anthropic returned no text content");
  }
  return {
    text,
    inputTokens: parsed.usage?.input_tokens ?? 0,
    outputTokens: parsed.usage?.output_tokens ?? 0,
  };
}

// ─── Route handler ─────────────────────────────────────────────────

export async function POST(req: Request) {
  try {
    const founder = await getFounderFromAuth(req);
    if (!founder) {
      return NextResponse.json(
        { error: "Not authenticated" },
        { status: 401 },
      );
    }

    const body = (await req.json().catch(() => ({}))) as {
      question?: string;
    };
    const question = (body.question || "").trim();
    if (!question) {
      return NextResponse.json(
        { error: "question is required" },
        { status: 400 },
      );
    }
    if (question.length > 2000) {
      return NextResponse.json(
        { error: "question too long (max 2000 chars)" },
        { status: 400 },
      );
    }

    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey) {
      return NextResponse.json(
        {
          error:
            "Anthropic API key not configured. Set ANTHROPIC_API_KEY in Vercel → Settings → Environment Variables, redeploy, and retry.",
        },
        { status: 503 },
      );
    }

    // ── Retrieval step 1: Conclusions (all of them) ──────────────
    const conclusions = await db.conclusion.findMany({
      where: { organizationId: founder.organizationId },
      orderBy: [
        { confidenceTier: "asc" }, // firm < founder < open < retired
        { createdAt: "desc" },
      ],
      take: MAX_CONCLUSIONS,
      select: {
        id: true,
        text: true,
        confidenceTier: true,
        topicHint: true,
        rationale: true,
      },
    });

    // ── Retrieval step 2: Upload chunks, keyword-scored ───────────
    //
    // Uploads are long. We can't stuff them all in context so we
    // chunk every candidate upload into paragraph-sized pieces and
    // keep the top TOP_CHUNKS by relevance to the question. This is
    // the "R" in RAG: a cheap, embedding-free retriever that still
    // pulls the right paragraph when the question uses words the
    // paragraph contains.
    //
    // Visibility rules mirror /library: ingested uploads belonging
    // to the org, not deleted, not another founder's private row.
    const uploadRows = await db.upload.findMany({
      where: {
        organizationId: founder.organizationId,
        deletedAt: null,
        status: "ingested",
        textContent: { not: null },
        OR: [{ visibility: { not: "private" } }, { founderId: founder.id }],
      },
      orderBy: { createdAt: "desc" },
      take: MAX_UPLOADS_TO_SCAN,
      select: {
        id: true,
        title: true,
        slug: true,
        textContent: true,
      },
    });

    const questionTokens = new Set(tokenize(question));
    const scoredChunks: ChunkRecord[] = [];
    const uploadMeta: UploadContext[] = [];

    for (const up of uploadRows) {
      if (!up.textContent) continue;
      uploadMeta.push({ id: up.id, title: up.title, slug: up.slug });
      const chunks = chunkText(up.textContent);
      for (let i = 0; i < chunks.length; i++) {
        const score = scoreChunk(chunks[i]!, questionTokens);
        if (score <= 0) continue;
        scoredChunks.push({
          uploadId: up.id,
          uploadTitle: up.title,
          uploadSlug: up.slug,
          chunkIndex: i,
          text: chunks[i]!,
          score,
        });
      }
    }

    // Keep the top K chunks overall (not per-upload — a single
    // highly-relevant upload should be able to dominate if that's
    // the right thing for the question).
    scoredChunks.sort((a, b) => b.score - a.score);
    const topChunks = scoredChunks.slice(0, TOP_CHUNKS);

    // ── Call Claude ────────────────────────────────────────────────
    const model = process.env.ASK_LLM_MODEL || DEFAULT_MODEL;
    const userMessage = buildUserMessage(question, conclusions, topChunks);

    let answer: string;
    let inputTokens = 0;
    let outputTokens = 0;
    try {
      const result = await callClaude(apiKey, model, userMessage);
      answer = result.text;
      inputTokens = result.inputTokens;
      outputTokens = result.outputTokens;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return NextResponse.json(
        { error: `Oracle call failed: ${message}` },
        { status: 502 },
      );
    }

    // ── Audit log (non-fatal) ──────────────────────────────────────
    await db.auditEvent
      .create({
        data: {
          organizationId: founder.organizationId,
          founderId: founder.id,
          action: "ask",
          detail: sanitizeAndCap(
            `Q: ${question.slice(0, 180)}${question.length > 180 ? "…" : ""} | ` +
              `model=${model} C=${conclusions.length} U=${topChunks.length} ` +
              `in=${inputTokens} out=${outputTokens}`,
            2_000,
          ),
        },
      })
      .catch(() => {
        /* non-fatal */
      });

    // ── Response ───────────────────────────────────────────────────
    // `sources` is a heterogeneous list — a `type` discriminator lets
    // the client render each kind with the right affordances
    // (conclusion → tier pill; upload → clickable title, link to
    // /post/<slug> when public).
    interface SourceEntry {
      type: "conclusion" | "upload";
      id: string;
      label: string;
      tier?: string;
      topic?: string;
      text: string;
      url?: string | null;
    }

    // Deduplicate upload sources by id — a single upload can
    // contribute multiple top chunks; we surface just one source
    // entry per upload but concatenate the top 2 chunks into `text`
    // so the founder sees why it was cited.
    const uploadSources = new Map<string, SourceEntry>();
    for (const c of topChunks) {
      if (uploadSources.has(c.uploadId)) {
        const existing = uploadSources.get(c.uploadId)!;
        if (existing.text.length < CHUNK_TARGET_CHARS * 2) {
          existing.text += "\n\n…\n\n" + c.text;
        }
      } else {
        uploadSources.set(c.uploadId, {
          type: "upload",
          id: c.uploadId,
          label: c.uploadTitle,
          text: c.text,
          url: c.uploadSlug ? `/post/${c.uploadSlug}` : null,
        });
      }
    }

    const sources: SourceEntry[] = [
      ...conclusions.map<SourceEntry>((c) => ({
        type: "conclusion",
        id: c.id,
        label: c.confidenceTier,
        tier: c.confidenceTier,
        topic: c.topicHint,
        text: c.text,
      })),
      ...uploadSources.values(),
    ];

    return NextResponse.json({
      question,
      answer,
      model,
      conclusionsInContext: conclusions.length,
      uploadsInContext: uploadSources.size,
      uploadChunksInContext: topChunks.length,
      inputTokens,
      outputTokens,
      sources,
    });
  } catch (error) {
    console.error("/api/ask error:", error);
    return NextResponse.json(
      {
        error: `Ask failed: ${error instanceof Error ? error.message : "unknown error"}`,
      },
      { status: 500 },
    );
  }
}
