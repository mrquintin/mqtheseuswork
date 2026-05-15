"use client";

/**
 * Bayesian view tab on the conclusion-detail page.
 *
 * Renders the derived Bayesian-belief layer for one conclusion: the
 * marginal probability that the conclusion holds, the credible interval
 * around it (reflecting CPT uncertainty — wide for a seeded guess,
 * tight once `bn_learning` has fit the CPT to resolved cases), the
 * inference method, and a ranked list of the most-influential parent
 * claims with their retraction sensitivity.
 *
 * Founder-side first. The banner makes the contract explicit: marginal
 * probabilities are not displayed publicly without founder review. The
 * data is fetched from the founder-only backend route via
 * `fetchBayesianView`, which degrades to a "not available" state when
 * the Python Bayesian layer is not deployed.
 *
 * The cascade tab remains the primary representation; this tab is a
 * derived view used for principled inference, not a replacement.
 */

import { useEffect, useState } from "react";

import {
  fetchBayesianView,
  formatCredibleInterval,
  formatProbability,
  methodCaption,
  sensitivityProse,
  type BayesianViewDTO,
  type ParentSensitivityDTO,
} from "@/lib/bayesianApi";

interface Props {
  conclusionId: string;
  /** Optional resolved claim texts, keyed by cascade node id. */
  claimTexts?: Record<string, string>;
}

type LoadState =
  | { status: "loading" }
  | { status: "unavailable" }
  | { status: "ready"; view: BayesianViewDTO };

const DIM = "var(--parchment-dim)";
const GOLD = "var(--gold)";
const AMBER = "var(--amber)";
const EMBER = "var(--ember)";

export default function BayesianView({ conclusionId, claimTexts }: Props) {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    fetchBayesianView(conclusionId, { signal: controller.signal })
      .then((view) => {
        setState(
          view ? { status: "ready", view } : { status: "unavailable" },
        );
      })
      .catch(() => setState({ status: "unavailable" }));
    return () => controller.abort();
  }, [conclusionId]);

  if (state.status === "loading") {
    return (
      <div style={{ padding: "0.75rem 0", color: DIM, fontSize: "0.85rem" }}>
        Computing Bayesian marginal…
      </div>
    );
  }

  if (state.status === "unavailable") {
    return (
      <div style={{ padding: "0.75rem 0", color: DIM, fontSize: "0.85rem" }}>
        The Bayesian-belief layer is not available for this conclusion. It is
        derived on demand from the cascade graph; if the Python inference
        service is not deployed, this view degrades rather than blocking the
        page.
      </div>
    );
  }

  const { view } = state;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <FounderBanner />
      <MarginalCard view={view} />
      <MethodLine view={view} />
      <ParentSensitivitySection view={view} claimTexts={claimTexts} />
      <DerivedViewFootnote view={view} />
    </div>
  );
}

function FounderBanner() {
  return (
    <div
      style={{
        border: `1px solid ${EMBER}`,
        borderRadius: "0.25rem",
        padding: "0.5rem 0.75rem",
        fontSize: "0.7rem",
        color: EMBER,
        background: "rgba(0,0,0,0.15)",
      }}
    >
      Founder-side tool. Marginal probabilities are not displayed publicly
      without founder review.
    </div>
  );
}

function MarginalCard({ view }: { view: BayesianViewDTO }) {
  const pct = view.marginal * 100;
  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "0.75rem",
          flexWrap: "wrap",
        }}
      >
        <span style={{ fontSize: "2rem", color: GOLD, fontVariantNumeric: "tabular-nums" }}>
          {formatProbability(view.marginal)}
        </span>
        <span style={{ fontSize: "0.8rem", color: DIM }}>
          marginal P(this conclusion holds)
        </span>
        {view.isEvidence && (
          <span style={{ fontSize: "0.7rem", color: AMBER }}>
            pinned by an evidence update
          </span>
        )}
      </div>

      {/* Marginal bar with the credible interval overlaid. */}
      <div
        style={{
          position: "relative",
          height: "0.6rem",
          marginTop: "0.5rem",
          background: "rgba(255,255,255,0.06)",
          borderRadius: "0.3rem",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: `${view.ciLow * 100}%`,
            width: `${Math.max(view.ciHigh - view.ciLow, 0) * 100}%`,
            top: 0,
            bottom: 0,
            background: "rgba(212,175,55,0.25)",
          }}
        />
        <div
          style={{
            position: "absolute",
            left: `calc(${pct}% - 1px)`,
            width: "2px",
            top: 0,
            bottom: 0,
            background: GOLD,
          }}
        />
      </div>
      <div style={{ fontSize: "0.7rem", color: DIM, marginTop: "0.35rem" }}>
        90% credible interval {formatCredibleInterval(view)} — reflects CPT
        uncertainty.{" "}
        {view.seeded
          ? "CPT is seeded from cascade weights (not yet fit to resolved cases)."
          : "CPT is fit to resolved cases."}
      </div>
    </div>
  );
}

function MethodLine({ view }: { view: BayesianViewDTO }) {
  return (
    <div style={{ fontSize: "0.72rem", color: DIM }}>
      {methodCaption(view)}
      {!view.exact && (
        <span style={{ color: AMBER }}>
          {" "}
          — graph exceeds the {view.exactLimit}-node exact-inference limit, so
          this is sampled, not exact.
        </span>
      )}
    </div>
  );
}

function ParentSensitivitySection({
  view,
  claimTexts,
}: {
  view: BayesianViewDTO;
  claimTexts?: Record<string, string>;
}) {
  if (view.parents.length === 0) {
    return (
      <div style={{ fontSize: "0.8rem", color: DIM }}>
        This conclusion has no parent claims in the Bayesian DAG — its marginal
        is a prior, not a derived belief.
      </div>
    );
  }
  return (
    <div>
      <h3
        style={{
          fontSize: "0.8rem",
          color: "var(--parchment)",
          margin: "0 0 0.5rem",
        }}
      >
        Most-influential parent claims
      </h3>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
        {view.parents.map((parent) => (
          <ParentRow
            key={parent.parentId}
            view={view}
            parent={parent}
            label={claimTexts?.[parent.parentId] ?? parent.parentRef}
          />
        ))}
      </div>
    </div>
  );
}

function ParentRow({
  view,
  parent,
  label,
}: {
  view: BayesianViewDTO;
  parent: ParentSensitivityDTO;
  label: string;
}) {
  // The sensitivity span: where the marginal lands if the parent is
  // retracted (low) vs held (high). The current marginal sits inside.
  const lo = Math.min(parent.pIfRetracted, parent.pIfHeld);
  const hi = Math.max(parent.pIfRetracted, parent.pIfHeld);
  return (
    <div
      style={{
        borderLeft: `2px solid ${AMBER}`,
        paddingLeft: "0.6rem",
      }}
    >
      <div
        style={{
          fontSize: "0.78rem",
          color: "var(--parchment)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        title={label}
      >
        {label}
      </div>
      <div
        style={{
          position: "relative",
          height: "0.5rem",
          marginTop: "0.3rem",
          background: "rgba(255,255,255,0.06)",
          borderRadius: "0.25rem",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: `${lo * 100}%`,
            width: `${Math.max(hi - lo, 0) * 100}%`,
            top: 0,
            bottom: 0,
            background: "rgba(199,125,42,0.35)",
            borderRadius: "0.25rem",
          }}
        />
        <div
          style={{
            position: "absolute",
            left: `calc(${view.marginal * 100}% - 1px)`,
            width: "2px",
            top: "-0.15rem",
            bottom: "-0.15rem",
            background: GOLD,
          }}
        />
      </div>
      <div style={{ fontSize: "0.68rem", color: DIM, marginTop: "0.25rem" }}>
        {sensitivityProse(view, parent)} · held → {formatProbability(parent.pIfHeld)} ·
        influence {formatProbability(parent.influence)}
      </div>
    </div>
  );
}

function DerivedViewFootnote({ view }: { view: BayesianViewDTO }) {
  return (
    <div
      style={{
        fontSize: "0.66rem",
        color: DIM,
        borderTop: "1px solid rgba(255,255,255,0.08)",
        paddingTop: "0.5rem",
      }}
    >
      Derived from the cascade graph ({view.nodeCount} truth-valued nodes).
      {view.droppedEdgeCount > 0 && (
        <>
          {" "}
          {view.droppedEdgeCount} cascade edge
          {view.droppedEdgeCount === 1 ? " was" : "s were"} excluded to keep the
          Bayesian projection acyclic.
        </>
      )}{" "}
      The cascade remains the primary representation; this is a derived view
      for principled inference.
    </div>
  );
}
