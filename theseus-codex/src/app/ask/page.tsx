import type { Metadata } from "next";
import { redirect } from "next/navigation";

import PublicAskBox from "@/components/PublicAskBox";
import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";

/**
 * Public inquiry page. The reader types a question into a single
 * box and we return the firm's relevant published conclusions,
 * articles, currents opinions, and open questions — ranked, snippeted,
 * and pilled with methodology + confidence.
 *
 * Pure retrieval. No generation lives on this surface; the founder
 * workspace's `/codex-ask` keeps the LLM-driven answer pipeline.
 * A reader who wants to know what the firm thinks gets a structured
 * pointer to the firm's actual public output, never a paraphrase.
 *
 * Route split (UI/UX Round 20 §3.6): `/ask` is public-only. A
 * signed-in operator who lands here — via a stale link, a shared
 * browser, or a deep link to `/ask?q=...` — is redirected to the
 * founder surface at `/codex-ask` (which preserves their query
 * string) so they never see the public retrieval surface in place
 * of the LLM-grounded one they expect.
 */

export const metadata: Metadata = {
  title: "Ask Theseus",
  description:
    "Search the firm's public conclusions, articles, opinions, and open questions.",
  openGraph: {
    title: "Ask Theseus",
    description:
      "Pose a question and see what the firm has actually published — conclusions, articles, currents opinions, and the open questions still on the table.",
    type: "website",
  },
};

export const dynamic = "force-dynamic";

type SearchParams = { q?: string | string[] };

function firstParam(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

export default async function PublicAskPage({
  searchParams,
}: {
  searchParams?: Promise<SearchParams>;
}) {
  const resolved = (await (searchParams ?? Promise.resolve<SearchParams>({}))) ?? {};
  const initialQuery = firstParam(resolved.q).slice(0, 500);

  const founder = await getFounder();
  if (founder) {
    const target = initialQuery
      ? `/codex-ask?q=${encodeURIComponent(initialQuery)}`
      : "/codex-ask";
    redirect(target);
  }

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <PublicHeader authed={false} />

      <div
        style={{
          margin: "0 auto",
          maxWidth: "920px",
          padding: "3rem 2rem 5rem",
        }}
      >
        <header style={{ marginBottom: "1.8rem" }}>
          <h1
            className="mono"
            style={{
              color: "var(--amber)",
              fontSize: "clamp(1.6rem, 3vw, 2.4rem)",
              letterSpacing: "0.16em",
              margin: 0,
              textTransform: "uppercase",
            }}
          >
            Ask the firm
          </h1>
          <p
            style={{
              color: "var(--parchment-dim)",
              fontFamily: "'EB Garamond', serif",
              fontSize: "1.05rem",
              lineHeight: 1.55,
              margin: "0.7rem 0 0",
              maxWidth: "44em",
            }}
          >
            One box, one question. We return what the firm has actually
            published on the topic — conclusions, articles, currents
            opinions, and the open questions still on the table. Snippets
            are excerpted, never rewritten. When the firm has not
            addressed your question directly, we say so and point you to
            the closest open question.
          </p>
        </header>

        <PublicAskBox mode="full" initialQuery={initialQuery} autoFocus />
      </div>
    </main>
  );
}
