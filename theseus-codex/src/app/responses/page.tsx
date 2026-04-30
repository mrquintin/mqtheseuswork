import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import RespondForm from "@/components/RespondForm";
import { getFounder } from "@/lib/auth";
import { listPublishedArticles, listPublishedConclusions } from "@/lib/conclusionsRead";

export const dynamic = "force-dynamic";
export const revalidate = 60;

export const metadata: Metadata = {
  title: "Responses",
};

type SearchParams = Record<string, string | string[] | undefined>;

function firstParam(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
}

function TabLink({ active, href, label }: { active: boolean; href: string; label: string }) {
  return (
    <Link
      className="mono"
      data-active-tab={active ? "true" : "false"}
      href={href}
      style={{
        border: `1px solid ${active ? "var(--amber)" : "var(--stroke)"}`,
        color: active ? "var(--amber)" : "var(--parchment-dim)",
        fontSize: "0.66rem",
        letterSpacing: "0.18em",
        padding: "0.45rem 0.7rem",
        textDecoration: "none",
        textTransform: "uppercase",
      }}
    >
      {label}
    </Link>
  );
}

export default async function ResponsesPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const activeTab = firstParam(sp.tab) === "articles" ? "articles" : "responses";
  const [founder, conclusions, articles] = await Promise.all([
    getFounder(),
    listPublishedConclusions(),
    listPublishedArticles(24),
  ]);
  const responseTargets = conclusions.filter(
    (row) => row.kind !== "ARTICLE" && !row.sourceConclusionId.startsWith("article:"),
  );

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container">
        <h1 className="public-title">Structured responses</h1>
        <p className="public-muted public-lede">
          Default: no inline comments. Responses are moderated, structured, and appear as a separate section when approved.
          Notable responses can be promoted to <strong>engaged</strong>, which triggers internal review of the conclusion.
        </p>

        <nav aria-label="Response page tabs" style={{ display: "flex", gap: "0.5rem", margin: "1.25rem 0" }}>
          <TabLink active={activeTab === "responses"} href="/responses" label="Responses" />
          <TabLink active={activeTab === "articles"} href="/responses?tab=articles" label="Articles" />
        </nav>

        {activeTab === "articles" ? (
          <section className="public-section">
            <h2>Articles</h2>
            {articles.length === 0 ? (
              <p className="public-muted">No generated articles have been published yet.</p>
            ) : (
              <ul className="public-response-list">
                {articles.map((article) => (
                  <li className="public-card" key={article.id}>
                    <p className="public-muted mono">{article.publishedAt.slice(0, 10)} · ARTICLE</p>
                    <h3 style={{ marginTop: 0 }}>
                      <Link href={`/c/${encodeURIComponent(article.slug)}`}>{article.payload.conclusionText}</Link>
                    </h3>
                    <p>{article.payload.evidenceSummary.slice(0, 260)}{article.payload.evidenceSummary.length > 260 ? "..." : ""}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        ) : (
          <RespondForm conclusions={responseTargets} />
        )}
      </main>
    </>
  );
}
