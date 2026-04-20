import Link from "next/link";
import { notFound } from "next/navigation";
import { db } from "@/lib/db";
import { resolveClaimTexts } from "@/lib/api/round3";
import { requireTenantContext } from "@/lib/tenant";
import PageHelp from "@/components/PageHelp";
import TabNav from "@/components/TabNav";
import ConclusionSigil from "./conclusion-sigil";
import ProvenanceTab from "./provenance-tab";
import CascadeTab from "./cascade-tab";
import PeerReviewTab from "./peer-review-tab";
import RelatedTab from "./related-tab";
import HistoryTab from "./history-tab";
import ActionsBar from "./actions-bar";

/**
 * Single-conclusion detail page.
 *
 * Tabs: Overview | Provenance | Cascade | Peer review. Tab state is
 * carried in `?tab=…` so URLs remain shareable.
 */

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "provenance", label: "Provenance" },
  { id: "cascade", label: "Cascade" },
  { id: "peer", label: "Peer review" },
  { id: "related", label: "Related" },
  { id: "history", label: "History" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function isTabId(value: string | undefined): value is TabId {
  return TABS.some((t) => t.id === value);
}

// Confidence-tier thresholds — kept near the UI that uses them so a
// reader lands on the same numbers that appear in the rendered tooltip.
// Mirrors the semantic bands described in noosphere ConfidenceTier.
const TIER_THRESHOLDS: Array<{ tier: string; min: number; color: string }> = [
  { tier: "firm", min: 0.85, color: "var(--gold)" },
  { tier: "founder", min: 0.65, color: "var(--amber)" },
  { tier: "open", min: 0.30, color: "var(--parchment)" },
  { tier: "speculative", min: 0, color: "var(--parchment-dim)" },
];

function tryParse(raw: string): string[] {
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v.map(String) : [];
  } catch {
    return [];
  }
}

export default async function ConclusionDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tab?: string; queued?: string }>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return null;
  }

  const { id } = await params;
  const sp = await searchParams;
  const activeTab: TabId = isTabId(sp.tab) ? sp.tab : "overview";

  const conclusion = await db.conclusion.findFirst({
    where: { id, organizationId: tenant.organizationId },
    include: {
      attributedFounder: true,
      organization: true,
      // Source uploads: the M:N bridge row plus the underlying Upload
      // metadata we need for the "Source documents" list in the Overview
      // tab. Filtered in app code to drop uploads that have been
      // soft-deleted since extraction (deletedAt IS NOT NULL).
      sources: {
        include: {
          upload: {
            select: {
              id: true,
              title: true,
              sourceType: true,
              createdAt: true,
              deletedAt: true,
            },
          },
        },
        orderBy: { createdAt: "desc" },
      },
    },
  });
  if (!conclusion) notFound();

  const supportIds = tryParse(conclusion.supportingPrincipleIds);
  const evidenceIds = tryParse(conclusion.evidenceChainClaimIds);
  const dissentIds = tryParse(conclusion.dissentClaimIds);

  // Batch one lookup for every ID across all three arrays — the helper
  // queries the Conclusion table by id, returns a Record<id, text>.
  // IDs that don't resolve are displayed as opaque IDs with a note.
  const allIds = [...supportIds, ...evidenceIds, ...dissentIds];
  const idTextMap = await resolveClaimTexts(tenant.organizationId, allIds);

  const sources = conclusion.sources
    .filter((cs) => !cs.upload.deletedAt)
    .map((cs) => ({
      uploadId: cs.upload.id,
      title: cs.upload.title,
      sourceType: cs.upload.sourceType,
    }));

  return (
    <main style={{ padding: "2rem 0" }}>
      <PageHelp
        title="Conclusion"
        purpose={`"${conclusion.text.slice(0, 140)}${conclusion.text.length > 140 ? "…" : ""}"`}
        howTo="The tabs below show everything the system knows about this conclusion: its origin (Provenance), its downstream consequences (Cascade), and peer reactions to it (Peer review)."
        sigil={<ConclusionSigil />}
      />

      <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "0 1.5rem" }}>
        {sp.queued && (
          <div
            className="portal-card"
            style={{
              padding: "0.6rem 1rem",
              marginBottom: "1rem",
              borderLeft: "3px solid var(--gold)",
              fontSize: "0.8rem",
              color: "var(--gold)",
            }}
          >
            Queued for publication review.
          </div>
        )}

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

          <ConfidenceContext confidence={conclusion.confidence} />

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

        <ActionsBar conclusionId={id} />

        <TabNav
          basePath={`/conclusions/${id}`}
          current={activeTab}
          tabs={TABS as unknown as ReadonlyArray<{ id: string; label: string }>}
        />

        <section style={{ marginTop: "1.5rem" }}>
          {activeTab === "overview" ? (
            <OverviewTab
              text={conclusion.text}
              supportIds={supportIds}
              evidenceIds={evidenceIds}
              dissentIds={dissentIds}
              idTextMap={idTextMap}
              sources={sources}
            />
          ) : activeTab === "provenance" ? (
            <ProvenanceTab conclusionId={id} />
          ) : activeTab === "cascade" ? (
            <CascadeTab conclusionId={id} />
          ) : activeTab === "peer" ? (
            <PeerReviewTab conclusionId={id} />
          ) : activeTab === "related" ? (
            <RelatedTab conclusionId={id} />
          ) : (
            <HistoryTab conclusionId={id} />
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

function ConfidenceContext({ confidence }: { confidence: number }) {
  const pct = Math.max(0, Math.min(1, confidence)) * 100;
  return (
    <div style={{ marginTop: "0.5rem", maxWidth: "30rem" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
        }}
      >
        <div
          style={{
            width: "12rem",
            height: "6px",
            background: "var(--border)",
            borderRadius: 3,
            position: "relative",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${pct.toFixed(1)}%`,
              height: "100%",
              background: "var(--gold)",
              borderRadius: 3,
            }}
          />
        </div>
        <span style={{ fontSize: "0.7rem", color: "var(--parchment-dim)" }}>
          {pct.toFixed(0)}%
        </span>
      </div>
      <details style={{ marginTop: "0.35rem" }}>
        <summary
          style={{
            cursor: "pointer",
            fontSize: "0.6rem",
            color: "var(--parchment-dim)",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
          }}
        >
          How confidence works
        </summary>
        <div
          style={{
            fontSize: "0.75rem",
            color: "var(--parchment-dim)",
            marginTop: "0.35rem",
            lineHeight: 1.6,
          }}
        >
          <p style={{ margin: 0 }}>
            Confidence is the system&apos;s assessment of epistemic warrant,
            computed from coherence scores, evidence strength, and peer-review
            outcomes.
          </p>
          <p style={{ margin: "0.35rem 0 0" }}>
            {TIER_THRESHOLDS.map((t, i) => (
              <span key={t.tier}>
                <strong style={{ color: t.color }}>
                  {t.tier[0].toUpperCase() + t.tier.slice(1)}
                </strong>
                {t.min > 0 ? ` (≥${(t.min * 100).toFixed(0)}%)` : " (<30%)"}
                {i < TIER_THRESHOLDS.length - 1 ? " · " : ""}
              </span>
            ))}
          </p>
        </div>
      </details>
    </div>
  );
}

function OverviewTab({
  text,
  supportIds,
  evidenceIds,
  dissentIds,
  idTextMap,
  sources,
}: {
  text: string;
  supportIds: string[];
  evidenceIds: string[];
  dissentIds: string[];
  idTextMap: Record<string, string>;
  sources: { uploadId: string; title: string; sourceType: string }[];
}) {
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

      <ExpandableIdList
        label="Supporting principles"
        ids={supportIds}
        idTextMap={idTextMap}
      />
      <ExpandableIdList
        label="Evidence chain claims"
        ids={evidenceIds}
        idTextMap={idTextMap}
      />
      <ExpandableIdList
        label="Dissenting claims"
        ids={dissentIds}
        idTextMap={idTextMap}
      />

      {sources.length > 0 && (
        <div>
          <div
            style={{
              fontFamily: "'Cinzel', serif",
              fontSize: "0.6rem",
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
              marginBottom: "0.5rem",
            }}
          >
            Source documents
          </div>
          {sources.map((s) => (
            <Link
              key={s.uploadId}
              href="/library"
              style={{
                display: "block",
                padding: "0.4rem 0.75rem",
                borderLeft: "2px solid var(--gold-dim)",
                marginBottom: "0.25rem",
                color: "var(--parchment)",
                textDecoration: "none",
                fontSize: "0.85rem",
              }}
            >
              {s.title}
              <span
                style={{
                  fontSize: "0.65rem",
                  color: "var(--parchment-dim)",
                  marginLeft: "0.5rem",
                }}
              >
                {s.sourceType}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function ExpandableIdList({
  label,
  ids,
  idTextMap,
}: {
  label: string;
  ids: string[];
  idTextMap: Record<string, string>;
}) {
  return (
    <details
      style={{
        padding: "0.75rem 1rem",
        border: "1px solid var(--border)",
        borderRadius: 2,
      }}
    >
      <summary
        style={{
          cursor: ids.length > 0 ? "pointer" : "default",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          listStyle: ids.length > 0 ? undefined : "none",
        }}
      >
        <span
          style={{
            fontFamily: "'Cinzel', serif",
            fontSize: "0.6rem",
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: "var(--parchment-dim)",
          }}
        >
          {label}
        </span>
        <span
          style={{
            fontSize: "1.1rem",
            color: "var(--gold)",
            fontFamily: "'Cinzel', serif",
          }}
        >
          {ids.length}
        </span>
      </summary>
      {ids.length === 0 ? null : (
        <div style={{ marginTop: "0.5rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {ids.map((id) => {
            const text = idTextMap[id];
            return (
              <div
                key={id}
                style={{
                  padding: "0.35rem 0.5rem",
                  borderLeft: "2px solid var(--border)",
                }}
              >
                {text ? (
                  <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--parchment)" }}>
                    {text}
                  </p>
                ) : (
                  <p
                    style={{
                      margin: 0,
                      fontSize: "0.75rem",
                      color: "var(--parchment-dim)",
                      fontStyle: "italic",
                    }}
                  >
                    {id.slice(0, 12)}… — text unavailable (may require Noosphere
                    connection)
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </details>
  );
}
