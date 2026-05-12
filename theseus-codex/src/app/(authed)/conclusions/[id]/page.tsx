import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { db } from "@/lib/db";
import { resolveClaimTexts } from "@/lib/api/round3";
import { founderDisplayName } from "@/lib/founderDisplay";
import {
  mqsForConclusion,
  profilesForConclusions,
  type PublicationMethodologyProfile,
} from "@/lib/methodologyProfiles";
import { canWrite } from "@/lib/roles";
import { requireTenantContext } from "@/lib/tenant";
import PublishToggle from "@/components/PublishToggle";
import TabNav from "@/components/TabNav";
import PublicationClient from "../../publication/PublicationClient";
import ProvenanceTab from "./provenance-tab";
import CascadeTab from "./cascade-tab";
import PeerReviewTab from "./peer-review-tab";
import BlindspotsPanel from "./BlindspotsPanel";
import RelatedTab from "./related-tab";
import HistoryTab from "./history-tab";
import LineagePanel from "./LineagePanel";
import ActionsBar from "./actions-bar";
import ConclusionKeymap from "./conclusion-keymap";
import MqsCard from "./MqsCard";
import FailureModesCard from "./FailureModesCard";
import { matchModesForConclusion } from "@/lib/failureModes";

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
  { id: "blindspots", label: "Geometric blindspots" },
  { id: "related", label: "Related" },
  { id: "lineage", label: "Lineage" },
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

const ACTIVE_REVIEW_STATES = new Set([
  "queued",
  "in_review",
  "needs_revision",
  "revising",
]);

function tryParse(raw: string): string[] {
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v.map(String) : [];
  } catch {
    return [];
  }
}

function formatDate(d: Date | string | null | undefined): string {
  if (!d) return "";
  const date = typeof d === "string" ? new Date(d) : d;
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString().slice(0, 10);
}

export default async function ConclusionDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tab?: string; queued?: string; deletionRequested?: string }>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return null;
  }

  const { id } = await params;
  const sp = await searchParams;
  const activeTab: TabId = isTabId(sp.tab) ? sp.tab : "overview";

  const [conclusion, publicationReviews, publishedVersions] = await Promise.all([
    db.conclusion.findFirst({
      where: { id, organizationId: tenant.organizationId },
      include: {
        attributedFounder: true,
        organization: true,
        sources: {
          include: {
            upload: {
              select: {
                id: true,
                title: true,
                sourceType: true,
                status: true,
                visibility: true,
                founderId: true,
                publishedAt: true,
                slug: true,
                createdAt: true,
                deletedAt: true,
              },
            },
          },
          orderBy: { createdAt: "desc" },
        },
      },
    }),
    db.publicationReview.findMany({
      where: { organizationId: tenant.organizationId, conclusionId: id },
      orderBy: { updatedAt: "desc" },
      take: 20,
      include: {
        target: true,
        reviewer: {
          select: { id: true, displayName: true, name: true, username: true },
        },
      },
    }),
    db.publishedConclusion.findMany({
      where: { organizationId: tenant.organizationId, sourceConclusionId: id },
      orderBy: { version: "desc" },
      take: 10,
      select: {
        id: true,
        slug: true,
        version: true,
        publishedAt: true,
        doi: true,
      },
    }),
  ]);
  if (!conclusion) notFound();

  const supportIds = tryParse(conclusion.supportingPrincipleIds);
  const evidenceIds = tryParse(conclusion.evidenceChainClaimIds);
  const dissentIds = tryParse(conclusion.dissentClaimIds);

  // Look for accepted Principle rows that reference this conclusion in
  // either their cited or full cluster set. The presence of such a row
  // is the closest available proxy for "this conclusion has been
  // abstracted into a principle". This is read-only; the classification
  // chip below reflects what already exists, not a new classification.
  const linkedPrinciples = await db.principle.findMany({
    where: {
      organizationId: tenant.organizationId,
      status: "accepted",
      OR: [
        { citedConclusionIds: { contains: `"${conclusion.id}"` } },
        { clusterConclusionIds: { contains: `"${conclusion.id}"` } },
      ],
    },
    orderBy: { convictionScore: "desc" },
    select: {
      id: true,
      text: true,
      convictionScore: true,
      domainsJson: true,
      citedConclusionIds: true,
    },
    take: 8,
  });

  const claimKind: "abstract_principle" | "empirical" | "decision_rule" | "unclassified" =
    linkedPrinciples.length > 0
      ? "abstract_principle"
      : conclusion.confidenceTier === "firm" || conclusion.confidenceTier === "founder"
        ? "empirical"
        : "unclassified";

  const allIds = [...supportIds, ...evidenceIds, ...dissentIds];
  const idTextMap = await resolveClaimTexts(tenant.organizationId, allIds);

  const sourceUploads = conclusion.sources
    .filter((cs) => !cs.upload.deletedAt)
    .map((cs) => ({
      uploadId: cs.upload.id,
      title: cs.upload.title,
      sourceType: cs.upload.sourceType,
      status: cs.upload.status,
      visibility: cs.upload.visibility,
      founderId: cs.upload.founderId,
      publishedAt: cs.upload.publishedAt,
      slug: cs.upload.slug,
    }));
  const sources = sourceUploads.map((source) => ({
    uploadId: source.uploadId,
    title: source.title,
    sourceType: source.sourceType,
  }));
  const writer = canWrite(tenant.role);
  const methodologyProfiles =
    (await profilesForConclusions(tenant.organizationId, [conclusion.id])).get(conclusion.id) ?? [];
  const mqs = await mqsForConclusion(tenant.organizationId, conclusion.id);
  const conclusionMethods = await db.conclusionMethod.findMany({
    where: { organizationId: tenant.organizationId, conclusionId: conclusion.id },
    select: { methodName: true },
  });
  const matchedFailureModes = matchModesForConclusion(
    conclusionMethods.map((m) => m.methodName),
    conclusion.text,
  );
  const publicationReviewProps = publicationReviews.map((r) => ({
    id: r.id,
    status: r.status,
    checklistJson: r.checklistJson,
    reviewerNotes: r.reviewerNotes,
    declineReason: r.declineReason,
    revisionAsk: r.revisionAsk,
    reviewerFounderId: r.reviewerFounderId,
    createdAt: r.createdAt.toISOString(),
    updatedAt: r.updatedAt.toISOString(),
    target: {
      id: r.target.id,
      text: r.target.text,
      topicHint: r.target.topicHint,
      confidenceTier: r.target.confidenceTier,
      confidence: r.target.confidence,
      createdAt: r.target.createdAt.toISOString(),
      methodologyProfiles,
    },
    reviewer: r.reviewer,
  }));
  const firmConclusionProps =
    conclusion.confidenceTier === "firm"
      ? [
          {
            id: conclusion.id,
            text: conclusion.text,
            topicHint: conclusion.topicHint,
            createdAt: conclusion.createdAt.toISOString(),
            methodologyProfiles,
          },
        ]
      : [];
  const toggleableSourceUploads = sourceUploads.filter(
    (source) =>
      writer &&
      source.status === "ingested" &&
      (tenant.role === "admin" || source.founderId === tenant.founderId),
  );

  const hasActiveReview = publicationReviewProps.some((r) =>
    ACTIVE_REVIEW_STATES.has(r.status),
  );
  const reviewPanelOpenDefault =
    Boolean(sp.queued) || hasActiveReview;
  const diagnosticsOpenDefault = matchedFailureModes.some(
    (m) => m.severity === "high",
  );

  async function requestConclusionDeletion(formData: FormData) {
    "use server";
    const cid = String(formData.get("conclusionId") || "");
    if (!cid) return;
    const t = await requireTenantContext();
    if (!t) redirect("/login");
    const existing = await db.conclusionDeletionRequest.findFirst({
      where: { conclusionId: cid, requesterId: t.founderId, status: "pending" },
      select: { id: true },
    });
    if (!existing) {
      await db.conclusionDeletionRequest.create({
        data: {
          conclusionId: cid,
          requesterId: t.founderId,
          reason: "Requested from conclusion detail page",
        },
      });
      await db.auditEvent.create({
        data: {
          organizationId: t.organizationId,
          founderId: t.founderId,
          action: "conclusion_deletion_request",
          detail: JSON.stringify({ conclusionId: cid, source: "detail-page" }),
        },
      });
    }
    revalidatePath(`/conclusions/${cid}`);
    redirect(`/conclusions/${cid}?deletionRequested=1`);
  }

  const tierColor =
    TIER_THRESHOLDS.find((t) => t.tier === conclusion.confidenceTier)?.color ??
    "var(--gold)";
  const updatedAtIso = conclusion.updatedAt ?? conclusion.createdAt;
  const attributionLabel = conclusion.attributedFounder
    ? founderDisplayName(conclusion.attributedFounder)
    : "";

  return (
    <main style={{ padding: "1.25rem 0 2rem" }}>
      <ConclusionKeymap conclusionId={id} canPublish={writer} />

      <div style={{ maxWidth: "1080px", margin: "0 auto", padding: "0 1.5rem" }}>
        {sp.queued && (
          <BannerLine tone="gold">Queued for publication review.</BannerLine>
        )}
        {sp.deletionRequested && (
          <BannerLine tone="amber">Deletion request submitted.</BannerLine>
        )}

        <ClaimSummary
          claim={conclusion.text}
          tier={conclusion.confidenceTier}
          tierColor={tierColor}
          confidence={conclusion.confidence}
          topicHint={conclusion.topicHint}
          attribution={attributionLabel}
          rationale={conclusion.rationale}
          createdAt={formatDate(conclusion.createdAt)}
          updatedAt={formatDate(updatedAtIso)}
          sources={sources}
          claimKind={claimKind}
          linkedPrinciples={linkedPrinciples.map((p) => ({ id: p.id, text: p.text }))}
        />

        <ActionsBar conclusionId={id} canWrite={writer} />

        <TabNav
          basePath={`/conclusions/${id}`}
          current={activeTab}
          tabs={TABS as unknown as ReadonlyArray<{ id: string; label: string }>}
        />

        <section style={{ marginTop: "1.25rem" }}>
          {activeTab === "overview" ? (
            <OverviewTab
              supportIds={supportIds}
              evidenceIds={evidenceIds}
              dissentIds={dissentIds}
              idTextMap={idTextMap}
              sources={sources}
              claimKind={claimKind}
            />
          ) : activeTab === "provenance" ? (
            <ProvenanceTab conclusionId={id} />
          ) : activeTab === "cascade" ? (
            <CascadeTab conclusionId={id} />
          ) : activeTab === "peer" ? (
            <PeerReviewTab conclusionId={id} />
          ) : activeTab === "blindspots" ? (
            <BlindspotsPanel
              conclusionId={id}
              organizationId={tenant.organizationId}
            />
          ) : activeTab === "related" ? (
            <RelatedTab conclusionId={id} />
          ) : activeTab === "lineage" ? (
            <LineagePanel conclusionId={id} />
          ) : (
            <HistoryTab conclusionId={id} />
          )}
        </section>

        <Disclosure
          id="review-and-publication"
          title="Review and publication"
          summary={reviewPanelSummary(publicationReviewProps, publishedVersions)}
          defaultOpen={reviewPanelOpenDefault}
        >
          <PublicationInlinePanel
            canUseReviewControls={writer}
            currentFounderId={tenant.founderId}
            firmConclusions={firmConclusionProps}
            publishedVersions={publishedVersions.map((version) => ({
              ...version,
              publishedAt: version.publishedAt.toISOString(),
            }))}
            reviews={publicationReviewProps}
            sourceUploads={toggleableSourceUploads}
          />
        </Disclosure>

        <Disclosure
          id="diagnostics"
          title="Diagnostics"
          summary={diagnosticsSummary(matchedFailureModes.length, mqs?.composite)}
          defaultOpen={diagnosticsOpenDefault}
        >
          <div style={{ display: "grid", gap: "0.85rem" }}>
            <FailureModesCard
              conclusionId={conclusion.id}
              matched={matchedFailureModes}
            />
            {mqs ? <MqsCard mqs={mqs} /> : null}
            <div
              style={{
                display: "flex",
                gap: "0.5rem",
                flexWrap: "wrap",
                paddingTop: "0.25rem",
              }}
            >
              <Link
                href={`/ops?panel=peer-review&target=${encodeURIComponent(id)}`}
                className="btn"
                style={{ fontSize: "0.65rem", textDecoration: "none" }}
              >
                Peer review history
              </Link>
              <Link
                href="/ops?panel=decay"
                className="btn"
                style={{ fontSize: "0.65rem", textDecoration: "none" }}
              >
                Decay dashboard
              </Link>
              <a
                href="/api/publication/export"
                className="btn"
                style={{ fontSize: "0.65rem", textDecoration: "none" }}
              >
                Export JSON
              </a>
              <Link
                href={`/conclusions/${id}?tab=lineage`}
                className="btn"
                style={{ fontSize: "0.65rem", textDecoration: "none" }}
              >
                Lineage tab
              </Link>
            </div>
          </div>
        </Disclosure>

        <AboutThisPage />

        <footer
          style={{
            marginTop: "1.75rem",
            paddingTop: "0.75rem",
            borderTop: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "1rem",
            flexWrap: "wrap",
          }}
        >
          <Link
            href="/knowledge?tab=conclusions"
            style={{
              fontFamily: "'Cinzel', serif",
              fontSize: "0.7rem",
              letterSpacing: "0.1em",
              color: "var(--parchment-dim)",
              textDecoration: "none",
            }}
          >
            ← Knowledge
          </Link>
          <details>
            <summary
              className="mono"
              style={{
                cursor: "pointer",
                color: "var(--parchment-dim)",
                fontSize: "0.6rem",
                letterSpacing: "0.18em",
                textTransform: "uppercase",
              }}
            >
              Request deletion
            </summary>
            <form action={requestConclusionDeletion} style={{ marginTop: "0.4rem" }}>
              <input type="hidden" name="conclusionId" value={id} />
              <button
                type="submit"
                className="btn"
                style={{
                  fontSize: "0.65rem",
                  color: "var(--ember)",
                  borderColor: "var(--ember)",
                }}
              >
                Submit deletion request
              </button>
            </form>
          </details>
        </footer>
      </div>
    </main>
  );
}

function BannerLine({
  children,
  tone,
}: {
  children: React.ReactNode;
  tone: "gold" | "amber";
}) {
  const color = tone === "gold" ? "var(--gold)" : "var(--amber)";
  return (
    <div
      style={{
        padding: "0.5rem 0.85rem",
        marginBottom: "0.85rem",
        borderLeft: `2px solid ${color}`,
        background: "var(--stone-light)",
        fontSize: "0.78rem",
        color,
      }}
    >
      {children}
    </div>
  );
}

const CLAIM_KIND_LABELS: Record<
  "abstract_principle" | "empirical" | "decision_rule" | "unclassified",
  { label: string; tooltip: string; color: string }
> = {
  abstract_principle: {
    color: "var(--gold)",
    label: "Abstract principle",
    tooltip:
      "This conclusion is referenced by an accepted Principle row, so the firm treats it as a load-bearing abstract rule.",
  },
  decision_rule: {
    color: "var(--amber)",
    label: "Decision rule",
    tooltip:
      "Reads as an action policy (a should/must rule) rather than a description of the world.",
  },
  empirical: {
    color: "var(--amber)",
    label: "Empirical observation",
    tooltip:
      "Firm/founder-tier claim grounded in source material; no abstract-principle link recorded yet.",
  },
  unclassified: {
    color: "var(--parchment-dim)",
    label: "Unclassified",
    tooltip:
      "Open or speculative; the firm has not assigned this conclusion to a principle or treated it as an empirical baseline.",
  },
};

function ClaimSummary({
  claim,
  tier,
  tierColor,
  confidence,
  topicHint,
  attribution,
  rationale,
  createdAt,
  updatedAt,
  sources,
  claimKind,
  linkedPrinciples,
}: {
  claim: string;
  tier: string;
  tierColor: string;
  confidence: number;
  topicHint: string;
  attribution: string;
  rationale: string;
  createdAt: string;
  updatedAt: string;
  sources: { uploadId: string; title: string; sourceType: string }[];
  claimKind: "abstract_principle" | "empirical" | "decision_rule" | "unclassified";
  linkedPrinciples: { id: string; text: string }[];
}) {
  const kind = CLAIM_KIND_LABELS[claimKind];
  const pct = Math.max(0, Math.min(1, confidence)) * 100;
  const showUpdated = updatedAt && updatedAt !== createdAt;
  return (
    <header style={{ marginBottom: "1rem" }}>
      <blockquote
        style={{
          margin: 0,
          padding: "0.85rem 1.15rem",
          borderLeft: `3px solid ${tierColor}`,
          background: "var(--stone-light)",
          fontSize: "1.1rem",
          lineHeight: 1.55,
          color: "var(--parchment)",
        }}
      >
        {claim}
      </blockquote>

      <dl
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.4rem 1rem",
          margin: "0.75rem 0 0",
          padding: 0,
          fontSize: "0.75rem",
          color: "var(--parchment-dim)",
          alignItems: "baseline",
        }}
      >
        <SummaryPair label="Tier">
          <span
            style={{
              color: tierColor,
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              fontFamily: "'Cinzel', serif",
              fontSize: "0.7rem",
            }}
          >
            {tier}
          </span>
        </SummaryPair>
        <SummaryPair label="Kind">
          <span
            data-claim-kind={claimKind}
            title={kind.tooltip}
            style={{
              color: kind.color,
              fontFamily: "'Cinzel', serif",
              fontSize: "0.7rem",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
            }}
          >
            {kind.label}
          </span>
        </SummaryPair>
        <SummaryPair label="Confidence">
          <span style={{ color: "var(--parchment)" }}>{pct.toFixed(0)}%</span>
        </SummaryPair>
        {topicHint ? (
          <SummaryPair label="Topic">
            <span style={{ color: "var(--parchment)" }}>{topicHint}</span>
          </SummaryPair>
        ) : null}
        {attribution ? (
          <SummaryPair label="Attributed to">
            <span style={{ color: "var(--parchment)" }}>{attribution}</span>
          </SummaryPair>
        ) : null}
        {createdAt ? (
          <SummaryPair label={showUpdated ? "Created" : "Recorded"}>
            <time dateTime={createdAt} style={{ color: "var(--parchment)" }}>
              {createdAt}
            </time>
          </SummaryPair>
        ) : null}
        {showUpdated ? (
          <SummaryPair label="Updated">
            <time dateTime={updatedAt} style={{ color: "var(--parchment)" }}>
              {updatedAt}
            </time>
          </SummaryPair>
        ) : null}
      </dl>

      {rationale ? (
        <p
          style={{
            margin: "0.65rem 0 0",
            fontSize: "0.9rem",
            color: "var(--parchment)",
            lineHeight: 1.55,
          }}
        >
          <span
            className="mono"
            style={{
              color: "var(--parchment-dim)",
              fontSize: "0.6rem",
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              marginRight: "0.45rem",
            }}
          >
            Rationale
          </span>
          {rationale}
        </p>
      ) : null}

      {linkedPrinciples.length > 0 ? (
        <div
          style={{
            margin: "0.55rem 0 0",
            display: "flex",
            flexWrap: "wrap",
            gap: "0.4rem",
            alignItems: "center",
          }}
        >
          <span
            className="mono"
            style={{
              color: "var(--parchment-dim)",
              fontSize: "0.6rem",
              letterSpacing: "0.18em",
              textTransform: "uppercase",
            }}
          >
            Abstracted into
          </span>
          {linkedPrinciples.map((p) => (
            <Link
              key={p.id}
              href={`/principles/${p.id}`}
              title={p.text}
              style={{
                border: "1px solid rgba(205, 151, 67, 0.55)",
                borderRadius: 2,
                color: "var(--amber)",
                fontSize: "0.74rem",
                padding: "0.15rem 0.5rem",
                textDecoration: "none",
              }}
            >
              {p.text.slice(0, 90)}
              {p.text.length > 90 ? "…" : ""}
            </Link>
          ))}
        </div>
      ) : null}

      {sources.length > 0 ? (
        <div
          style={{
            margin: "0.65rem 0 0",
            display: "flex",
            flexWrap: "wrap",
            gap: "0.4rem",
            alignItems: "center",
          }}
        >
          <span
            className="mono"
            style={{
              color: "var(--parchment-dim)",
              fontSize: "0.6rem",
              letterSpacing: "0.18em",
              textTransform: "uppercase",
            }}
          >
            Source
          </span>
          {sources.map((s) => (
            <Link
              key={s.uploadId}
              href="/knowledge?tab=library"
              style={{
                padding: "0.15rem 0.55rem",
                border: "1px solid var(--border)",
                borderRadius: 2,
                color: "var(--parchment)",
                textDecoration: "none",
                fontSize: "0.75rem",
                lineHeight: 1.4,
              }}
            >
              {s.title}
              <span
                style={{
                  marginLeft: "0.35rem",
                  color: "var(--parchment-dim)",
                  fontSize: "0.65rem",
                }}
              >
                {s.sourceType}
              </span>
            </Link>
          ))}
        </div>
      ) : null}
    </header>
  );
}

function SummaryPair({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: "inline-flex", alignItems: "baseline", gap: "0.35rem" }}>
      <dt
        className="mono"
        style={{
          color: "var(--parchment-dim)",
          fontSize: "0.58rem",
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          margin: 0,
        }}
      >
        {label}
      </dt>
      <dd style={{ margin: 0 }}>{children}</dd>
    </div>
  );
}

function Disclosure({
  id,
  title,
  summary,
  defaultOpen,
  children,
}: {
  id: string;
  title: string;
  summary?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  return (
    <details
      id={id}
      open={defaultOpen}
      style={{
        marginTop: "1.25rem",
        border: "1px solid var(--border)",
        borderRadius: 2,
        padding: "0.6rem 0.85rem",
      }}
    >
      <summary
        style={{
          cursor: "pointer",
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "0.75rem",
          flexWrap: "wrap",
          listStyle: "none",
        }}
      >
        <span
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.62rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
          }}
        >
          {title}
        </span>
        {summary ? (
          <span style={{ color: "var(--parchment-dim)", fontSize: "0.75rem" }}>
            {summary}
          </span>
        ) : null}
      </summary>
      <div style={{ marginTop: "0.85rem" }}>{children}</div>
    </details>
  );
}

function AboutThisPage() {
  return (
    <details
      style={{
        marginTop: "1.25rem",
        padding: "0.5rem 0.85rem",
      }}
    >
      <summary
        className="mono"
        style={{
          cursor: "pointer",
          color: "var(--parchment-dim)",
          fontSize: "0.6rem",
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          listStyle: "none",
        }}
      >
        About this page
      </summary>
      <div
        style={{
          marginTop: "0.5rem",
          fontSize: "0.82rem",
          color: "var(--parchment-dim)",
          lineHeight: 1.55,
          maxWidth: "64ch",
        }}
      >
        <p style={{ margin: 0 }}>
          The tabs above show what the system knows about this conclusion:
          its origin (Provenance), downstream consequences (Cascade), and
          peer reactions (Peer review). Confidence is computed from
          coherence scores, evidence strength, and peer-review outcomes.
        </p>
        <p style={{ margin: "0.4rem 0 0" }}>
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
  );
}

function reviewPanelSummary(
  reviews: Array<{ status: string; updatedAt: string }>,
  publishedVersions: Array<{ version: number; publishedAt: Date }>,
): string {
  const latestPublished = publishedVersions[0];
  const latestReview = reviews[0];
  const parts: string[] = [];
  if (latestPublished) {
    parts.push(`v${latestPublished.version} published`);
  } else {
    parts.push("not published");
  }
  if (latestReview) {
    parts.push(`review ${latestReview.status}`);
  }
  return parts.join(" · ");
}

function diagnosticsSummary(modeCount: number, mqsComposite: number | undefined): string {
  const parts: string[] = [];
  if (mqsComposite !== undefined) {
    parts.push(`MQS ${Math.round(mqsComposite * 100)}%`);
  }
  parts.push(`${modeCount} matched failure mode${modeCount === 1 ? "" : "s"}`);
  return parts.join(" · ");
}

function PublicationInlinePanel({
  canUseReviewControls,
  currentFounderId,
  firmConclusions,
  publishedVersions,
  reviews,
  sourceUploads,
}: {
  canUseReviewControls: boolean;
  currentFounderId: string;
  firmConclusions: Array<{
    id: string;
    text: string;
    topicHint: string;
    createdAt: string;
    methodologyProfiles: PublicationMethodologyProfile[];
  }>;
  publishedVersions: Array<{
    id: string;
    slug: string;
    version: number;
    publishedAt: string;
    doi: string;
  }>;
  reviews: Array<{
    id: string;
    status: string;
    checklistJson: string;
    reviewerNotes: string;
    declineReason: string;
    revisionAsk: string;
    reviewerFounderId: string | null;
    createdAt: string;
    updatedAt: string;
    target: {
      id: string;
      text: string;
      topicHint: string;
      confidenceTier: string;
      confidence: number;
      createdAt: string;
      methodologyProfiles: PublicationMethodologyProfile[];
    };
    reviewer: {
      id: string;
      displayName: string | null;
      name: string;
      username: string;
    } | null;
  }>;
  sourceUploads: Array<{
    uploadId: string;
    title: string;
    sourceType: string;
    status: string;
    visibility: string;
    founderId: string;
    publishedAt: Date | null;
    slug: string | null;
  }>;
}) {
  const latest = publishedVersions[0];

  return (
    <div style={{ display: "grid", gap: "0.85rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
        <p style={{ color: "var(--parchment-dim)", fontSize: "0.82rem", margin: 0 }}>
          Publication review for this conclusion. Source-post visibility toggles
          live below.
        </p>
        {latest ? (
          <Link
            className="btn"
            href={`/c/${encodeURIComponent(latest.slug)}/v/${latest.version}`}
            style={{ alignSelf: "flex-start", fontSize: "0.65rem", textDecoration: "none" }}
          >
            Public v{latest.version}
          </Link>
        ) : null}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.7rem", alignItems: "center" }}>
        <span className="mono" style={{ color: latest ? "var(--gold)" : "var(--parchment-dim)", fontSize: "0.62rem", letterSpacing: "0.18em", textTransform: "uppercase" }}>
          {latest ? `Published ${latest.publishedAt.slice(0, 10)}` : "No published version"}
        </span>
        {reviews[0] ? (
          <span className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.62rem", letterSpacing: "0.18em", textTransform: "uppercase" }}>
            Latest review: {reviews[0].status}
          </span>
        ) : null}
      </div>

      {publishedVersions.length > 1 ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.45rem" }}>
          {publishedVersions.slice(1).map((version) => (
            <Link
              key={version.id}
              href={`/c/${encodeURIComponent(version.slug)}/v/${version.version}`}
              style={{ color: "var(--gold-dim)", fontSize: "0.72rem", textDecoration: "none" }}
            >
              v{version.version}
            </Link>
          ))}
        </div>
      ) : null}

      {sourceUploads.length > 0 ? (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: "0.85rem" }}>
          <h3
            className="mono"
            style={{
              color: "var(--parchment-dim)",
              fontSize: "0.58rem",
              letterSpacing: "0.2em",
              margin: "0 0 0.55rem",
              textTransform: "uppercase",
            }}
          >
            Source post visibility
          </h3>
          <div style={{ display: "grid", gap: "0.5rem" }}>
            {sourceUploads.map((source) => (
              <div
                key={source.uploadId}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "0.8rem",
                  flexWrap: "wrap",
                }}
              >
                <span style={{ color: "var(--parchment)", fontSize: "0.82rem" }}>
                  {source.title}
                  <span style={{ color: "var(--parchment-dim)", marginLeft: "0.45rem" }}>
                    {source.sourceType}
                  </span>
                </span>
                <PublishToggle
                  uploadId={source.uploadId}
                  initialPublishedAt={source.publishedAt}
                  initialSlug={source.slug}
                />
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {canUseReviewControls ? (
        <PublicationClient
          currentFounderId={currentFounderId}
          firmConclusions={firmConclusions}
          reviews={reviews}
        />
      ) : reviews.length > 0 ? (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: "0.85rem" }}>
          {reviews.map((review) => (
            <p key={review.id} style={{ color: "var(--parchment-dim)", fontSize: "0.78rem", margin: "0.25rem 0" }}>
              {review.status} · updated {review.updatedAt.slice(0, 10)}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function OverviewTab({
  supportIds,
  evidenceIds,
  dissentIds,
  idTextMap,
  sources,
  claimKind,
}: {
  supportIds: string[];
  evidenceIds: string[];
  dissentIds: string[];
  idTextMap: Record<string, string>;
  sources: { uploadId: string; title: string; sourceType: string }[];
  claimKind: "abstract_principle" | "empirical" | "decision_rule" | "unclassified";
}) {
  const lists: Array<{ label: string; ids: string[] }> = [
    { label: "Supporting principles", ids: supportIds },
    { label: "Evidence chain claims", ids: evidenceIds },
    { label: "Dissenting claims", ids: dissentIds },
  ];
  const nonEmpty = lists.filter((l) => l.ids.length > 0);
  const empty = lists.filter((l) => l.ids.length === 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {nonEmpty.map((l) => (
        <ExpandableIdList
          key={l.label}
          label={l.label}
          ids={l.ids}
          idTextMap={idTextMap}
        />
      ))}

      {empty.length > 0 ? (
        <p
          className="mono"
          style={{
            margin: 0,
            color: "var(--parchment-dim)",
            fontSize: "0.7rem",
            letterSpacing: "0.12em",
          }}
        >
          {empty
            .map((l) => `${l.label.toLowerCase()}: none`)
            .join(" · ")}
        </p>
      ) : null}

      <CasesSection claimKind={claimKind} />


      {sources.length > 0 && (
        <div>
          <div
            className="mono"
            style={{
              fontSize: "0.6rem",
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
              marginBottom: "0.4rem",
            }}
          >
            Source documents
          </div>
          {sources.map((s) => (
            <Link
              key={s.uploadId}
              href="/knowledge?tab=library"
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

function CasesSection({
  claimKind,
}: {
  claimKind: "abstract_principle" | "empirical" | "decision_rule" | "unclassified";
}) {
  const hint =
    claimKind === "abstract_principle"
      ? "Empirical case studies that support, bound, or contradict this principle are not yet persisted to the Codex DB. When the case extractor's rows land, supporting and contradicting cases will appear here."
      : "Empirical case rows are not yet persisted in the Codex. Once the case extractor's output is wired in, observed situations citing this conclusion will surface here.";
  return (
    <details
      data-section="cases"
      style={{
        padding: "0.65rem 0.85rem",
        border: "1px solid var(--border)",
        borderRadius: 2,
      }}
    >
      <summary
        style={{
          cursor: "pointer",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <span
          className="mono"
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.6rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          Supporting / contradicting cases
        </span>
        <span
          className="mono"
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.6rem",
            letterSpacing: "0.12em",
          }}
        >
          0
        </span>
      </summary>
      <p
        style={{
          color: "var(--parchment-dim)",
          fontSize: "0.8rem",
          lineHeight: 1.55,
          margin: "0.45rem 0 0",
        }}
      >
        {hint}
      </p>
    </details>
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
        padding: "0.65rem 0.85rem",
        border: "1px solid var(--border)",
        borderRadius: 2,
      }}
    >
      <summary
        style={{
          cursor: "pointer",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <span
          className="mono"
          style={{
            fontSize: "0.6rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--parchment-dim)",
          }}
        >
          {label}
        </span>
        <span
          style={{
            fontSize: "1rem",
            color: "var(--gold)",
            fontFamily: "'Cinzel', serif",
          }}
        >
          {ids.length}
        </span>
      </summary>
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
    </details>
  );
}
