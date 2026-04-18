import Link from "next/link";
import { notFound } from "next/navigation";
import { db } from "@/lib/db";
import PageHelp from "@/components/PageHelp";
import TabNav from "@/components/TabNav";
import ConclusionSigil from "./conclusion-sigil";
import ProvenanceTab from "./provenance-tab";
import CascadeTab from "./cascade-tab";
import PeerReviewTab from "./peer-review-tab";

/**
 * Single-conclusion detail page.
 *
 * Before consolidation: the three tab components in this directory existed
 * as orphans — the `/conclusions/[id]` URL returned 404 because no
 * `page.tsx` had ever been wired up. To see a specific conclusion's
 * lineage, users had to navigate to `/provenance`, `/cascade/[id]`, and
 * `/peer-review/[id]` separately, never landing on a single "this
 * conclusion" page.
 *
 * After: one page at `/conclusions/[id]` with four tabs:
 *   - Overview  : the conclusion record itself (text, rationale, confidence)
 *   - Provenance: extraction chain (how we got from claim → conclusion)
 *   - Cascade   : inference tree (what downstream claims depend on this)
 *   - Peer      : founder reviews of the conclusion
 *
 * Each tab is a server component; selecting a tab is a URL query param
 * (`?tab=provenance`) so bookmarks and the browser back button work.
 */

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "provenance", label: "Provenance" },
  { id: "cascade", label: "Cascade" },
  { id: "peer", label: "Peer review" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function isTabId(value: string | undefined): value is TabId {
  return TABS.some((t) => t.id === value);
}

export default async function ConclusionDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const activeTab: TabId = isTabId(sp.tab) ? sp.tab : "overview";

  const conclusion = await db.conclusion.findUnique({
    where: { id },
    include: { attributedFounder: true, organization: true },
  });
  if (!conclusion) notFound();

  return (
    <main style={{ padding: "2rem 0" }}>
      <PageHelp
        title="Conclusion"
        purpose={`"${conclusion.text.slice(0, 140)}${conclusion.text.length > 140 ? "…" : ""}"`}
        howTo="The tabs below show everything the system knows about this conclusion: its origin (Provenance), its downstream consequences (Cascade), and peer reactions to it (Peer review)."
        sigil={<ConclusionSigil />}
      />

      <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "0 1.5rem" }}>
        <header style={{ marginBottom: "1.5rem" }}>
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: "1rem",
              flexWrap: "wrap",
            }}
          >
            <span
              style={{
                fontFamily: "'Cinzel', serif",
                fontSize: "0.65rem",
                letterSpacing: "0.15em",
                textTransform: "uppercase",
                padding: "0.2rem 0.6rem",
                border: "1px solid var(--gold-dim)",
                color: "var(--gold)",
                borderRadius: 2,
              }}
            >
              {conclusion.confidenceTier}
            </span>
            <span
              style={{
                fontSize: "0.75rem",
                color: "var(--parchment-dim)",
              }}
            >
              Confidence {(conclusion.confidence * 100).toFixed(0)}%
              {conclusion.attributedFounder
                ? ` · Attributed to ${conclusion.attributedFounder.name}`
                : ""}
              {conclusion.topicHint ? ` · ${conclusion.topicHint}` : ""}
            </span>
          </div>
          {conclusion.rationale ? (
            <p
              style={{
                marginTop: "0.75rem",
                fontSize: "0.95rem",
                color: "var(--parchment)",
                fontStyle: "italic",
              }}
            >
              Rationale: {conclusion.rationale}
            </p>
          ) : null}
        </header>

        <TabNav
          basePath={`/conclusions/${id}`}
          current={activeTab}
          tabs={TABS as unknown as ReadonlyArray<{ id: string; label: string }>}
        />

        <section style={{ marginTop: "1.5rem" }}>
          {activeTab === "overview" ? (
            <OverviewTab
              text={conclusion.text}
              rationale={conclusion.rationale}
              createdAt={conclusion.createdAt}
              supportingPrincipleIds={conclusion.supportingPrincipleIds}
              evidenceChainClaimIds={conclusion.evidenceChainClaimIds}
              dissentClaimIds={conclusion.dissentClaimIds}
            />
          ) : activeTab === "provenance" ? (
            <ProvenanceTab conclusionId={id} />
          ) : activeTab === "cascade" ? (
            <CascadeTab conclusionId={id} />
          ) : (
            <PeerReviewTab conclusionId={id} />
          )}
        </section>

        <nav style={{ marginTop: "2rem" }}>
          <Link
            href="/conclusions"
            style={{
              fontFamily: "'Cinzel', serif",
              fontSize: "0.7rem",
              letterSpacing: "0.1em",
              color: "var(--parchment-dim)",
              textDecoration: "none",
            }}
          >
            ← All conclusions
          </Link>
        </nav>
      </div>
    </main>
  );
}

function OverviewTab({
  text,
  rationale,
  createdAt,
  supportingPrincipleIds,
  evidenceChainClaimIds,
  dissentClaimIds,
}: {
  text: string;
  rationale: string;
  createdAt: Date;
  supportingPrincipleIds: string;
  evidenceChainClaimIds: string;
  dissentClaimIds: string;
}) {
  const tryParse = (raw: string): unknown[] => {
    try {
      const v = JSON.parse(raw);
      return Array.isArray(v) ? v : [];
    } catch {
      return [];
    }
  };
  const support = tryParse(supportingPrincipleIds);
  const evidence = tryParse(evidenceChainClaimIds);
  const dissent = tryParse(dissentClaimIds);
  // `rationale` and `createdAt` are surfaced in the header; included in the
  // Overview block only when additional narrative context helps the reader.
  void rationale;
  void createdAt;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <blockquote
        style={{
          margin: 0,
          padding: "1rem 1.25rem",
          borderLeft: "3px solid var(--gold)",
          background: "var(--stone-light)",
          fontSize: "1.1rem",
          lineHeight: 1.6,
          color: "var(--parchment)",
        }}
      >
        {text}
      </blockquote>
      <dl
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          gap: "1rem",
          margin: 0,
        }}
      >
        <MetaBlock label="Supporting principles" count={support.length} />
        <MetaBlock label="Evidence chain claims" count={evidence.length} />
        <MetaBlock label="Dissenting claims" count={dissent.length} />
      </dl>
    </div>
  );
}

function MetaBlock({ label, count }: { label: string; count: number }) {
  return (
    <div
      style={{
        padding: "0.75rem 1rem",
        border: "1px solid var(--border)",
        borderRadius: 2,
      }}
    >
      <div
        style={{
          fontFamily: "'Cinzel', serif",
          fontSize: "0.6rem",
          letterSpacing: "0.15em",
          textTransform: "uppercase",
          color: "var(--parchment-dim)",
        }}
      >
        {label}
      </div>
      <div
        style={{
          marginTop: "0.35rem",
          fontSize: "1.5rem",
          color: "var(--gold)",
          fontFamily: "'Cinzel', serif",
        }}
      >
        {count}
      </div>
    </div>
  );
}
