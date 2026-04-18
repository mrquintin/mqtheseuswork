/**
 * Live status of the auto-processing pipeline.
 *
 * The dashboard calls this to decide whether to show a "Setup
 * auto-processing" banner vs. a "Auto-processing active" pill.
 *
 * Returns a small JSON blob:
 * {
 *   "vercel": {
 *     "github_dispatch_token": boolean,   // GITHUB_DISPATCH_TOKEN on Vercel
 *     "github_dispatch_repo": string,     // effective repo slug
 *     "openai_key": boolean,              // OPENAI_API_KEY for Whisper
 *   },
 *   "github": {
 *     // We can't verify GitHub secrets from Vercel — only the user's
 *     // own view of Actions UI can do that. But we include hints.
 *     "workflow_url": "https://github.com/<repo>/actions/workflows/…",
 *     "known_to_fail_without": ["CODEX_DATABASE_URL"],
 *   },
 *   "configured": boolean,                // true if the webhook path works
 *   "summary": string,                    // short human-readable line
 * }
 *
 * Requires the same auth as the rest of /api — session cookie OR API key.
 */
import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";

export async function GET(req: Request) {
  const founder = await getFounderFromAuth(req);
  if (!founder) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const hasToken = Boolean(process.env.GITHUB_DISPATCH_TOKEN);
  const hasOpenAI = Boolean(process.env.OPENAI_API_KEY);
  const repo = process.env.GITHUB_DISPATCH_REPO || "mrquintin/mqtheseuswork";
  const workflowUrl = `https://github.com/${repo}/actions/workflows/noosphere-process-uploads.yml`;

  const configured = hasToken;
  const summary = hasToken
    ? `Webhook dispatch active → ${repo} · ` +
      (hasOpenAI ? "LLM mode (OpenAI)" : "Naive mode (set OPENAI_API_KEY for LLM)")
    : "Auto-processing not configured — set GITHUB_DISPATCH_TOKEN on Vercel + CODEX_DATABASE_URL on GitHub";

  return NextResponse.json({
    vercel: {
      github_dispatch_token: hasToken,
      github_dispatch_repo: repo,
      openai_key: hasOpenAI,
    },
    github: {
      workflow_url: workflowUrl,
      known_to_fail_without: ["CODEX_DATABASE_URL"],
    },
    configured,
    summary,
    docs: "docs/Auto_Processing_Setup.md",
  });
}
