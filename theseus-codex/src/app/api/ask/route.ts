import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";

/**
 * Ask the Codex.
 *
 * The central value proposition of the system: "upload your material,
 * then ask the LLM questions grounded in what you've uploaded." This
 * endpoint is the minimum viable realisation of that:
 *
 *   1. Authenticate (cookie session OR Bearer API key — same as /api/upload).
 *   2. Collect the organisation's Conclusion rows. These are the atomic
 *      claims that `noosphere ingest-from-codex` has distilled from
 *      every previous upload — already filtered, classified, and
 *      attributed. Much denser than raw upload text.
 *   3. Build a grounded prompt: "Here are the firm's recorded beliefs.
 *      Answer ONLY from them. If the firm hasn't said, say so."
 *   4. Call OpenAI. Return the answer + the ids of the Conclusions
 *      that were provided as context, so the UI can show citations.
 *
 * Why NOT vector search yet
 * -------------------------
 * At ≤ a few hundred Conclusions, sending them all as plain context is
 * simpler, cheaper to explain, and strictly higher-recall than a
 * retrieval step that could miss relevant claims. We truncate to the
 * 120 most-recent ~200-character rows (≈ 4-6k tokens of context) to
 * stay well under any modern chat-model's limit, with room for the
 * answer. When a firm grows past that, a proper embedding-based RAG
 * path becomes worth the complexity — at which point this endpoint
 * gets a retrieve-then-ask inner loop but its external contract
 * (question in, answer + sources out) stays unchanged.
 *
 * Why NOT raw Upload.textContent as context
 * -----------------------------------------
 * Raw uploads are 10-100× longer than Conclusions. Including them in
 * the prompt burns tokens on boilerplate. If the user wants to ask
 * about something specific that didn't become a Conclusion yet, the
 * correct answer is "run `noosphere ingest-from-codex` on that upload
 * first, so the claim gets surfaced", not "pretend the raw PDF is
 * structured context."
 */

const SYSTEM_PROMPT = `You are the Theseus Codex's oracle.

You answer questions from within a single firm's corpus of recorded beliefs, called Conclusions. Each Conclusion is an atomic claim the firm has surfaced, tagged with a confidenceTier:

  firm     — the firm stands behind this belief in its strongest form.
  founder  — a single founder's conviction; not yet firm-wide.
  open     — an unresolved coherence tension, under active review.
  retired  — a belief the firm formerly held, now retracted.

Rules:
1. Answer ONLY from the Conclusions provided below.
2. When you make a claim, name the Conclusion ids that support it in square brackets, e.g. "[c-a5f7…]".
3. Weight firm and founder tiers more than open; never cite retired as current belief.
4. If the firm has not recorded a position on the question, say so explicitly. Do not speculate.
5. Prefer concision. One-to-three sentence answers are ideal; longer only if the question genuinely demands it.`;

interface ConclusionForContext {
  id: string;
  text: string;
  confidenceTier: string;
  topicHint: string;
  rationale: string;
}

function buildUserMessage(question: string, conclusions: ConclusionForContext[]): string {
  if (conclusions.length === 0) {
    return `The firm has recorded no Conclusions yet.\n\nQuestion: ${question}`;
  }
  const rendered = conclusions
    .map(
      (c, i) =>
        `[${i + 1}] id=${c.id.slice(0, 10)} · tier=${c.confidenceTier} · topic=${c.topicHint || "general"}\n     ${c.text}`,
    )
    .join("\n\n");
  return `CORPUS OF FIRM CONCLUSIONS (${conclusions.length} total):\n\n${rendered}\n\n———\n\nQuestion: ${question}\n\nAnswer grounded in the corpus above. Cite ids.`;
}

export async function POST(req: Request) {
  try {
    const founder = await getFounderFromAuth(req);
    if (!founder) {
      return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }

    const body = (await req.json().catch(() => ({}))) as { question?: string };
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

    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
      return NextResponse.json(
        {
          error:
            "OpenAI API key not configured. Set OPENAI_API_KEY in Vercel → Settings → Environment Variables, redeploy, and retry.",
        },
        { status: 503 },
      );
    }

    // Gather recent Conclusions as context. We take up to 120 most
    // recent rows; 120 rows × ~200 char/row ≈ 24k chars ≈ 6k tokens,
    // leaving ample headroom under gpt-4o-mini's 128k context.
    const conclusions = await db.conclusion.findMany({
      where: { organizationId: founder.organizationId },
      orderBy: [
        // Prioritise the firmer beliefs. Within each tier, newest first.
        { confidenceTier: "asc" }, // "firm" < "founder" < "open" < "retired" alphabetically
        { createdAt: "desc" },
      ],
      take: 120,
      select: {
        id: true,
        text: true,
        confidenceTier: true,
        topicHint: true,
        rationale: true,
      },
    });

    const userMessage = buildUserMessage(question, conclusions);

    // Call OpenAI. Using the chat completions endpoint for maximum
    // model flexibility — the caller can swap `model` by env var if
    // they want Claude or a different GPT without touching code.
    const model = process.env.ASK_LLM_MODEL || "gpt-4o-mini";
    const { default: OpenAI } = await import("openai");
    const openai = new OpenAI({ apiKey });
    const completion = await openai.chat.completions.create({
      model,
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: userMessage },
      ],
      temperature: 0.3, // grounded / deterministic-ish; we're citing, not brainstorming
      max_tokens: 800,
    });

    const answer = completion.choices[0]?.message?.content?.trim() || "";
    if (!answer) {
      return NextResponse.json(
        { error: "LLM returned empty response" },
        { status: 502 },
      );
    }

    // Log the query as an AuditEvent. Useful for usage analytics +
    // provenance if the firm ever wants to retroactively verify "what
    // did the oracle tell us on this date?" Question text is
    // user-supplied so scrub NUL / control bytes before insert — a
    // stray 0x00 from a paste otherwise fails the whole audit.
    const { sanitizeAndCap } = await import("@/lib/sanitizeText");
    await db.auditEvent
      .create({
        data: {
          organizationId: founder.organizationId,
          founderId: founder.id,
          action: "ask",
          detail: sanitizeAndCap(
            `Q: ${question.slice(0, 180)}${question.length > 180 ? "…" : ""}`,
            2_000,
          ),
        },
      })
      .catch(() => {
        // Non-fatal — don't deny the caller their answer over an audit-log failure.
      });

    return NextResponse.json({
      question,
      answer,
      model,
      conclusionsInContext: conclusions.length,
      sources: conclusions.map((c) => ({
        id: c.id,
        tier: c.confidenceTier,
        topic: c.topicHint,
        text: c.text,
      })),
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
