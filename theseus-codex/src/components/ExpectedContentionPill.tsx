/**
 * ExpectedContentionPill — pre-review prediction of swarm contention.
 *
 * The reviewer-agreement model (noosphere.peer_review.agreement_model)
 * predicts, before the swarm runs, how tightly the reviewers will agree
 * on a conclusion. This pill surfaces that prediction at review time so
 * the founder knows when to expect contention — and shows the routing
 * decision the prediction drove, with the cost saving and the coverage
 * it cost sitting side by side.
 *
 * Presentational only: no hooks, no client JS. The expandable detail
 * uses a native <details> element so it works in a server component.
 * The component renders nothing when no prediction is available — the
 * model is a predictive aid, and a missing artifact is a silent no-op,
 * never an error.
 */

export interface ContentionDriver {
  feature: string;
  contribution: number;
}

export interface ContentionPrediction {
  /** "low" | "moderate" | "high" — the founder-facing contention label. */
  expectedContention: string;
  /** Predicted inter-reviewer agreement, 0..1. */
  predictedAgreement: number;
  /** "contested" | "nominal" | "consensus". */
  band: string;
  /** "expand" | "keep" | "shrink" | "keep_full_swarm_override". */
  action: string;
  rationale: string;
  costDeltaUsd: number;
  coverageDelta: number;
  costSavingUsd: number;
  coverageLoss: number;
  baselineMix: string[];
  providerMix: string[];
  founderOverride: boolean;
  modelTrainedAt: string;
  generatedAt: string;
  calibrationSkill: number | null;
  topDrivers: ContentionDriver[];
}

type Tone = {
  fg: string;
  border: string;
  bg: string;
};

function toneFor(expectedContention: string): Tone {
  switch (expectedContention) {
    case "high":
      return {
        fg: "var(--ember)",
        border: "var(--ember)",
        bg: "rgba(172, 54, 37, 0.12)",
      };
    case "low":
      return {
        fg: "rgba(160, 211, 170, 0.95)",
        border: "rgba(160, 211, 170, 0.7)",
        bg: "rgba(95, 126, 93, 0.12)",
      };
    default:
      return {
        fg: "var(--amber)",
        border: "var(--amber-dim, var(--amber))",
        bg: "rgba(205, 151, 67, 0.1)",
      };
  }
}

function actionLabel(action: string): string {
  switch (action) {
    case "expand":
      return "swarm expanded — more reviewers, more cost";
    case "shrink":
      return "swarm shrunk — fewer reviewers, lower cost";
    case "keep_full_swarm_override":
      return "full swarm kept — founder override";
    default:
      return "default swarm kept";
  }
}

/** "sourcemix__frontier_pair" → "source mix · frontier pair". */
function humanizeFeature(feature: string): string {
  return feature
    .replace(/__/g, " · ")
    .replace(/_/g, " ")
    .replace(/topic emb (\d+)/, "topic embedding $1");
}

function formatUsd(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : value > 0 ? "+" : "";
  return `${sign}$${abs.toFixed(4)}`;
}

export default function ExpectedContentionPill({
  prediction,
}: {
  prediction: ContentionPrediction | null;
}) {
  if (!prediction) return null;

  const tone = toneFor(prediction.expectedContention);
  const agreementPct = Math.round(prediction.predictedAgreement * 100);
  const label = prediction.expectedContention.toUpperCase();
  const skill = prediction.calibrationSkill;

  return (
    <details
      className="portal-card"
      style={{
        padding: "0.6rem 0.9rem",
        borderLeft: `3px solid ${tone.border}`,
        background: tone.bg,
        marginBottom: "1rem",
        fontSize: "0.78rem",
      }}
    >
      <summary
        style={{
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: "0.6rem",
          flexWrap: "wrap",
          listStyle: "none",
        }}
      >
        <span
          className="mono"
          style={{
            color: tone.fg,
            border: `1px solid ${tone.border}`,
            borderRadius: "2px",
            padding: "0.12rem 0.45rem",
            fontSize: "0.58rem",
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            whiteSpace: "nowrap",
          }}
        >
          Expected contention · {label}
        </span>
        <span style={{ color: "var(--parchment)" }}>
          Model predicts{" "}
          <strong style={{ color: tone.fg }}>{agreementPct}%</strong>{" "}
          inter-reviewer agreement
        </span>
        <span style={{ color: "var(--parchment-dim)", fontSize: "0.7rem" }}>
          — {actionLabel(prediction.action)}
        </span>
      </summary>

      <div
        style={{
          marginTop: "0.6rem",
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
          color: "var(--parchment-dim)",
          lineHeight: 1.55,
        }}
      >
        <p style={{ margin: 0, color: "var(--parchment)" }}>
          {prediction.rationale}
        </p>

        {/* Cost saving and coverage cost, always reported together — the
            firm never sees a cheaper number without the coverage it
            bought or gave up sitting beside it. */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
            gap: "0.4rem",
          }}
        >
          <StatCell
            label="Cost vs default swarm"
            value={formatUsd(prediction.costDeltaUsd)}
            tone={prediction.costDeltaUsd <= 0 ? "good" : "warn"}
          />
          <StatCell
            label="Reviewer coverage Δ"
            value={
              prediction.coverageDelta > 0
                ? `+${prediction.coverageDelta}`
                : `${prediction.coverageDelta}`
            }
            tone={prediction.coverageDelta < 0 ? "warn" : "neutral"}
          />
          <StatCell
            label="Routed reviewers"
            value={`${prediction.providerMix.length} (${prediction.providerMix.join(", ")})`}
            tone="neutral"
          />
          <StatCell
            label="Default reviewers"
            value={`${prediction.baselineMix.length} (${prediction.baselineMix.join(", ")})`}
            tone="neutral"
          />
        </div>

        {prediction.coverageLoss > 0 && (
          <p style={{ margin: 0, color: "var(--amber)", fontSize: "0.72rem" }}>
            Routing dropped {prediction.coverageLoss} reviewer
            {prediction.coverageLoss === 1 ? "" : "s"} for cost discipline.
            The prediction is an aid, not a gate — request the full swarm
            if this conclusion warrants it.
          </p>
        )}

        {prediction.founderOverride && (
          <p style={{ margin: 0, color: "var(--gold)", fontSize: "0.72rem" }}>
            Founder override active: the full default swarm ran regardless
            of the prediction.
          </p>
        )}

        {prediction.topDrivers.length > 0 && (
          <div>
            <div
              className="mono"
              style={{
                fontSize: "0.58rem",
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: "var(--gold-dim)",
                marginBottom: "0.25rem",
              }}
            >
              Why this prediction
            </div>
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                display: "flex",
                flexDirection: "column",
                gap: "0.15rem",
              }}
            >
              {prediction.topDrivers.map((d) => (
                <li
                  key={d.feature}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: "0.5rem",
                    fontSize: "0.72rem",
                  }}
                >
                  <span>{humanizeFeature(d.feature)}</span>
                  <span
                    className="mono"
                    style={{
                      color:
                        d.contribution >= 0
                          ? "rgba(160, 211, 170, 0.9)"
                          : "var(--ember)",
                    }}
                  >
                    {d.contribution >= 0 ? "+" : "−"}
                    {Math.abs(d.contribution).toFixed(3)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div
          className="mono"
          style={{ fontSize: "0.62rem", color: "var(--parchment-dim)" }}
        >
          model trained {prediction.modelTrainedAt.slice(0, 16) || "—"} ·
          held-out skill{" "}
          {skill === null ? "—" : `${(skill * 100).toFixed(0)}%`}
          {skill !== null && skill <= 0
            ? " (no skill — treat as noise)"
            : ""}{" "}
          · band {prediction.band}
        </div>
      </div>
    </details>
  );
}

function StatCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "good" | "warn" | "neutral";
}) {
  const color =
    tone === "good"
      ? "rgba(160, 211, 170, 0.95)"
      : tone === "warn"
        ? "var(--amber)"
        : "var(--parchment)";
  return (
    <div
      style={{
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: "2px",
        padding: "0.35rem 0.5rem",
      }}
    >
      <div
        className="mono"
        style={{
          fontSize: "0.55rem",
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          color: "var(--parchment-dim)",
        }}
      >
        {label}
      </div>
      <div style={{ color, fontSize: "0.75rem", marginTop: "0.1rem" }}>
        {value}
      </div>
    </div>
  );
}
