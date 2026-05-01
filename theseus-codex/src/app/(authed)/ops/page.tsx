import Link from "next/link";
import AdversarialPage from "../adversarial/page";
import ContradictionsPage from "../contradictions/page";
import DecayPage from "../decay/page";
import EvalPage from "../eval/page";
import FoundersPage from "../founders/page";
import MethodsPage from "../methods/page";
import OpenQuestionsPage from "../open-questions/page";
import PeerReviewPage from "../peer-review/[conclusionId]/page";
import PostMortemPage from "../post-mortem/page";
import ProvenancePage from "../provenance/page";
import ReviewQueuePage from "../q/review/page";
import RigorGatePage from "../rigor-gate/page";
import RigorGateDetailPage from "../rigor-gate/[submissionId]/page";
import ScoreboardPage from "../scoreboard/page";

type OpsSearchParams = {
  panel?: string;
  target?: string;
  ledger?: string;
  asOf?: string;
  showResolved?: string;
  author?: string;
  engage?: string;
};

const OPS_PANELS = [
  {
    id: "provenance",
    label: "Provenance",
    detail: "Extraction records and source chains.",
  },
  {
    id: "contradictions",
    label: "Contradictions",
    detail: "Claim pairs whose coherence layers disagree.",
  },
  {
    id: "peer-review",
    label: "Peer review",
    detail: "Per-conclusion review history, opened from a conclusion detail page.",
  },
  {
    id: "decay",
    label: "Decay",
    detail: "Confidence freshness and revalidation.",
  },
  {
    id: "rigor-gate",
    label: "Rigor gate",
    detail: "Mutation approvals, rejections, and overrides.",
  },
  {
    id: "methods",
    label: "Methods",
    detail: "Registered extraction and review methods.",
  },
] as const;

export default async function OpsPage({
  searchParams,
}: {
  searchParams: Promise<OpsSearchParams>;
}) {
  const sp = await searchParams;
  const panel = sp.panel || "overview";
  const target = firstPathSegment(sp.target);

  if (panel === "provenance") return <ProvenancePage />;
  if (panel === "eval") return <EvalPage />;
  if (panel === "contradictions") {
    return (
      <ContradictionsPage
        searchParams={Promise.resolve({
          asOf: sp.asOf,
          showResolved: sp.showResolved,
        })}
      />
    );
  }
  if (panel === "peer-review") {
    if (!target) return <PeerReviewIndex />;
    return (
      <PeerReviewPage
        params={Promise.resolve({ conclusionId: target })}
        searchParams={Promise.resolve({ ledger: sp.ledger })}
      />
    );
  }
  if (panel === "open-questions") return <OpenQuestionsPage />;
  if (panel === "adversarial") return <AdversarialPage />;
  if (panel === "layer-review") return <ReviewQueuePage />;
  if (panel === "calibration") {
    return (
      <ScoreboardPage
        searchParams={Promise.resolve({
          author: sp.author,
          engage: sp.engage,
        })}
      />
    );
  }
  if (panel === "post-mortem") return <PostMortemPage />;
  if (panel === "decay") {
    return <DecayPage searchParams={Promise.resolve({ ledger: sp.ledger })} />;
  }
  if (panel === "rigor-gate") {
    if (target) {
      return (
        <RigorGateDetailPage
          params={Promise.resolve({ submissionId: target })}
          searchParams={Promise.resolve({ ledger: sp.ledger })}
        />
      );
    }
    return <RigorGatePage searchParams={Promise.resolve({ ledger: sp.ledger })} />;
  }
  if (panel === "methods") return <MethodsPage />;
  if (panel === "founders") {
    return <FoundersPage searchParams={Promise.resolve({ asOf: sp.asOf })} />;
  }

  return <OpsOverview />;
}

function firstPathSegment(value: string | undefined): string {
  return (value || "").split("/").filter(Boolean)[0] || "";
}

function OpsOverview() {
  return (
    <main style={{ maxWidth: "1040px", margin: "0 auto", padding: "3rem 2rem" }}>
      <header style={{ marginBottom: "1.75rem" }}>
        <h1
          style={{
            fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
            fontSize: "1.8rem",
            letterSpacing: "0.16em",
            color: "var(--amber)",
            margin: 0,
            textShadow: "var(--glow-sm)",
          }}
        >
          Ops
        </h1>
        <p
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.62rem",
            letterSpacing: "0.24em",
            textTransform: "uppercase",
          }}
        >
          Advanced tooling · Audit surfaces · Founder operations
        </p>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "0.85rem" }}>
        {OPS_PANELS.map((panel) => (
          <Link
            key={panel.id}
            href={`/ops?panel=${panel.id}`}
            className="portal-card"
            style={{
              color: "inherit",
              display: "block",
              padding: "1rem 1.1rem",
              textDecoration: "none",
            }}
          >
            <h2
              style={{
                color: "var(--gold)",
                fontFamily: "'Cinzel', serif",
                fontSize: "0.9rem",
                letterSpacing: "0.1em",
                margin: 0,
              }}
            >
              {panel.label}
            </h2>
            <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem", lineHeight: 1.5, margin: "0.5rem 0 0" }}>
              {panel.detail}
            </p>
          </Link>
        ))}
      </div>
    </main>
  );
}

function PeerReviewIndex() {
  return (
    <main style={{ maxWidth: "840px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Peer review
      </h1>
      <div className="portal-card" style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)", lineHeight: 1.6 }}>
        Peer review is now opened from an individual conclusion. Go to{" "}
        <Link href="/knowledge?tab=conclusions" style={{ color: "var(--gold)" }}>
          Knowledge
        </Link>
        , choose a conclusion, then use its peer review tab or action bar.
      </div>
    </main>
  );
}
