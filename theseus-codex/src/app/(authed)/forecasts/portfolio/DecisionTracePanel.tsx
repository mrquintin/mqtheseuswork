import type { CSSProperties } from "react";

import {
  DECISION_ACTION_BLURBS,
  METRIC_DEFINITIONS,
  type DecisionAction,
  type DecisionFrame,
  type DecisionMetric,
  type DecisionRule,
  type DecisionTrace,
  type FrameVerdict,
} from "@/lib/forecastsTypes";

const wrapStyle: CSSProperties = {
  border: "1px solid rgba(232, 225, 211, 0.12)",
  borderRadius: 6,
  display: "grid",
  gap: "0.7rem",
  padding: "0.85rem",
};

const gridStyle: CSSProperties = {
  display: "grid",
  gap: "0.55rem",
  gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
};

const cellStyle: CSSProperties = {
  background: "rgba(232, 225, 211, 0.03)",
  border: "1px solid rgba(232, 225, 211, 0.08)",
  borderRadius: 4,
  padding: "0.45rem 0.55rem",
};

const labelStyle: CSSProperties = {
  color: "var(--amber-dim)",
  fontSize: "0.58rem",
  letterSpacing: "0.18em",
  textTransform: "uppercase",
};

const valueStyle: CSSProperties = {
  color: "var(--parchment)",
  display: "block",
  fontSize: "0.96rem",
  marginTop: "0.15rem",
};

function actionColor(action: DecisionAction): string {
  switch (action) {
    case "LIVE_CANDIDATE":
      return "var(--amber)";
    case "PAPER_TRADE":
      return "rgba(127, 196, 143, 0.95)";
    case "WATCH":
      return "rgba(212, 178, 90, 0.95)";
    case "REDUCE":
    case "EXIT":
      return "var(--ember)";
    case "HEDGE":
      return "rgba(170, 159, 220, 0.95)";
    default:
      return "var(--parchment-dim)";
  }
}

function fmtPct(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return `${(value * 100).toFixed(1)}%`;
}

function fmtSignedPct(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(1)} pp`;
}

function fmtScalar(value: number): string {
  if (!Number.isFinite(value)) return "n/a";
  return value.toFixed(3);
}

function fmtUsd(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 2,
    style: "currency",
  }).format(value);
}

export function ActionBadge({
  action,
  size = "md",
}: {
  action: DecisionAction;
  size?: "sm" | "md";
}) {
  const accent = actionColor(action);
  return (
    <span
      className="mono"
      data-decision-action={action}
      style={{
        border: `1px solid ${accent}`,
        borderRadius: 999,
        color: accent,
        fontSize: size === "sm" ? "0.58rem" : "0.68rem",
        letterSpacing: "0.12em",
        padding: size === "sm" ? "0.12rem 0.42rem" : "0.22rem 0.55rem",
      }}
    >
      {action}
    </span>
  );
}

function MetricRow({ metric }: { metric: DecisionMetric }) {
  const definition = METRIC_DEFINITIONS[metric.name];
  const valueColor = metric.lowConfidence ? "var(--parchment-dim)" : "var(--parchment)";
  return (
    <div style={cellStyle} title={definition || metric.detail}>
      <div style={labelStyle}>
        {metric.name}
        {metric.lowConfidence ? " · low-conf" : ""}
      </div>
      <strong style={{ ...valueStyle, color: valueColor }}>{fmtScalar(metric.value)}</strong>
      <div
        className="mono"
        style={{
          color: "var(--parchment-dim)",
          fontSize: "0.6rem",
          marginTop: "0.2rem",
        }}
      >
        range [{metric.rangeLow.toFixed(0)}, {metric.rangeHigh.toFixed(0)}] · {metric.method}
      </div>
      {metric.detail ? (
        <div style={{ color: "var(--parchment-dim)", fontSize: "0.66rem", marginTop: "0.2rem" }}>
          {metric.detail}
        </div>
      ) : null}
    </div>
  );
}

const FRAME_VERDICT_COLORS: Record<FrameVerdict, string> = {
  ABSTAIN: "var(--parchment-dim)",
  EXIT: "var(--ember)",
  HARD_STOP: "var(--ember)",
  HEDGE: "rgba(170, 159, 220, 0.95)",
  REDUCE: "var(--ember)",
  SUPPORT: "rgba(127, 196, 143, 0.95)",
  WATCH: "rgba(212, 178, 90, 0.95)",
};

function FrameRow({ frame }: { frame: DecisionFrame }) {
  const color = FRAME_VERDICT_COLORS[frame.verdict] ?? "var(--parchment-dim)";
  return (
    <div
      data-frame-name={frame.name}
      data-frame-verdict={frame.verdict}
      style={{
        ...cellStyle,
        borderColor: frame.assumptionsStable
          ? "rgba(232, 225, 211, 0.08)"
          : "rgba(212, 178, 90, 0.45)",
      }}
    >
      <div style={{ ...labelStyle, color }}>
        {frame.name} → {frame.verdict}
        {frame.assumptionsStable ? "" : " · assumptions unstable"}
      </div>
      {frame.detail ? (
        <div style={{ color: "var(--parchment)", fontSize: "0.74rem", marginTop: "0.2rem" }}>
          {frame.detail}
        </div>
      ) : null}
      {frame.reasons.length > 0 ? (
        <ul style={{ color: "var(--parchment-dim)", margin: "0.25rem 0 0", paddingLeft: "1rem" }}>
          {frame.reasons.map((reason, idx) => (
            <li key={`${idx}-${reason}`} style={{ fontSize: "0.7rem" }}>
              {reason}
            </li>
          ))}
        </ul>
      ) : null}
      {frame.failureModes.length > 0 ? (
        <div className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.6rem", marginTop: "0.25rem" }}>
          fails-if: {frame.failureModes.join(" · ")}
        </div>
      ) : null}
    </div>
  );
}

function RuleRow({ rule }: { rule: DecisionRule }) {
  const color = !rule.fired
    ? "var(--parchment-dim)"
    : rule.passed
      ? "rgba(127, 196, 143, 0.95)"
      : "var(--ember)";
  const status = !rule.fired ? "skipped" : rule.passed ? "pass" : "fail";
  return (
    <li
      data-rule-name={rule.name}
      data-rule-status={status}
      style={{
        borderBottom: "1px solid rgba(232, 225, 211, 0.06)",
        padding: "0.35rem 0",
      }}
    >
      <span className="mono" style={{ color, fontSize: "0.7rem" }}>
        [{rule.kind}] {rule.name} → {status.toUpperCase()}
      </span>
      {rule.detail ? (
        <div style={{ color: "var(--parchment-dim)", fontSize: "0.68rem", marginTop: "0.18rem" }}>
          {rule.detail}
        </div>
      ) : null}
    </li>
  );
}

export default function DecisionTracePanel({
  trace,
  prose,
}: {
  trace: DecisionTrace | null;
  prose?: string | null;
}) {
  if (trace === null) {
    return (
      <div data-decision-trace="missing" style={wrapStyle}>
        <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.7rem" }}>
          No decision trace recorded yet — the forecast generator has not produced metrics for this market.
        </span>
      </div>
    );
  }

  const edgeMetric = trace.metrics.find((m) => m.name === "market_mispricing_edge");
  const edgeValue = edgeMetric?.value ?? trace.edge;

  return (
    <div data-decision-trace={trace.action} style={wrapStyle}>
      <div
        style={{
          alignItems: "center",
          display: "flex",
          flexWrap: "wrap",
          gap: "0.7rem",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.6rem", alignItems: "center" }}>
          <ActionBadge action={trace.action} />
          {trace.side ? (
            <span className="mono" style={{ color: "var(--parchment)", fontSize: "0.7rem" }}>
              side {trace.side}
            </span>
          ) : null}
          <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.66rem" }}>
            {trace.traceVersion || "decision_metrics@?"}
          </span>
        </div>
        <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.66rem" }}>
          trace confidence {fmtScalar(trace.confidence)}
        </span>
      </div>

      <p style={{ color: "var(--parchment-dim)", fontSize: "0.72rem", margin: 0 }}>
        {DECISION_ACTION_BLURBS[trace.action]}
      </p>

      <div style={gridStyle}>
        <div style={cellStyle}>
          <div style={labelStyle}>Firm probability (YES)</div>
          <strong style={valueStyle}>{fmtPct(trace.firmProbabilityYes)}</strong>
        </div>
        <div style={cellStyle}>
          <div style={labelStyle}>Market price (YES)</div>
          <strong style={valueStyle}>{fmtPct(trace.marketYesPrice)}</strong>
        </div>
        <div style={cellStyle}>
          <div style={labelStyle}>Edge</div>
          <strong style={valueStyle}>{fmtSignedPct(edgeValue)}</strong>
        </div>
        <div style={cellStyle}>
          <div style={labelStyle}>Suggested stake</div>
          <strong style={valueStyle}>{fmtUsd(trace.stakeRecommendationUsd)}</strong>
        </div>
      </div>

      <details>
        <summary
          className="mono"
          style={{
            color: "var(--amber-dim)",
            cursor: "pointer",
            fontSize: "0.66rem",
            letterSpacing: "0.16em",
            textTransform: "uppercase",
          }}
        >
          Metrics ({trace.metrics.length})
        </summary>
        <div style={{ ...gridStyle, marginTop: "0.55rem" }}>
          {trace.metrics.map((metric) => (
            <MetricRow key={metric.name} metric={metric} />
          ))}
        </div>
      </details>

      <details>
        <summary
          className="mono"
          style={{
            color: "var(--amber-dim)",
            cursor: "pointer",
            fontSize: "0.66rem",
            letterSpacing: "0.16em",
            textTransform: "uppercase",
          }}
        >
          Rule graph ({trace.rules.filter((r) => r.fired).length} fired / {trace.rules.length} total)
        </summary>
        <ul style={{ listStyle: "none", margin: "0.4rem 0 0", padding: 0 }}>
          {trace.rules.map((rule) => (
            <RuleRow key={rule.name} rule={rule} />
          ))}
        </ul>
      </details>

      {trace.frames.length > 0 ? (
        <details data-decision-frames="present">
          <summary
            className="mono"
            style={{
              color: "var(--amber-dim)",
              cursor: "pointer",
              fontSize: "0.66rem",
              letterSpacing: "0.16em",
              textTransform: "uppercase",
            }}
          >
            Decision frames ({trace.frames.length})
            {trace.synthesis ? (
              <span style={{ color: "var(--parchment-dim)", marginLeft: "0.5rem" }}>
                · synthesis → {trace.synthesis.action} · agreement {fmtScalar(trace.synthesis.agreement)}
              </span>
            ) : null}
          </summary>
          <div style={{ ...gridStyle, marginTop: "0.55rem" }}>
            {trace.frames.map((frame) => (
              <FrameRow key={frame.name} frame={frame} />
            ))}
          </div>
          {trace.synthesis && trace.synthesis.reasons.length > 0 ? (
            <ul style={{ color: "var(--parchment-dim)", margin: "0.4rem 0 0", paddingLeft: "1.1rem" }}>
              {trace.synthesis.reasons.map((reason, idx) => (
                <li key={`syn-${idx}`} style={{ fontSize: "0.7rem" }}>
                  {reason}
                </li>
              ))}
            </ul>
          ) : null}
        </details>
      ) : null}

      {trace.analogicalTransfer ? (
        <details data-analogical-transfer="present">
          <summary
            className="mono"
            style={{
              color: "var(--amber-dim)",
              cursor: "pointer",
              fontSize: "0.66rem",
              letterSpacing: "0.16em",
              textTransform: "uppercase",
            }}
          >
            Empirical transfer · best stance {trace.analogicalTransfer.bestStance || "—"} ·{" "}
            {trace.analogicalTransfer.recommendations.length} recommendation
            {trace.analogicalTransfer.recommendations.length === 1 ? "" : "s"}
          </summary>
          <div style={{ marginTop: "0.5rem", display: "grid", gap: "0.45rem" }}>
            {trace.analogicalTransfer.recommendations.length === 0 ? (
              <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.66rem" }}>
                no transfer candidates produced for this market
              </span>
            ) : (
              trace.analogicalTransfer.recommendations.map((rec) => (
                <div key={rec.principleId} style={cellStyle}>
                  <div style={labelStyle}>
                    {rec.stance} · {fmtScalar(rec.confidence)}
                  </div>
                  <div style={{ color: "var(--parchment)", fontSize: "0.78rem", marginTop: "0.2rem" }}>
                    {rec.canonicalStatement || rec.principleId}
                  </div>
                  {rec.closestCaseIds.length > 0 ? (
                    <div
                      className="mono"
                      style={{ color: "var(--parchment-dim)", fontSize: "0.6rem", marginTop: "0.18rem" }}
                    >
                      closest cases: {rec.closestCaseIds.slice(0, 3).join(", ")}
                      {rec.closestCaseIds.length > 3 ? "…" : ""}
                    </div>
                  ) : null}
                  {rec.reasons.length > 0 ? (
                    <ul style={{ color: "var(--parchment-dim)", margin: "0.25rem 0 0", paddingLeft: "1rem" }}>
                      {rec.reasons.slice(0, 3).map((reason, idx) => (
                        <li key={`r-${idx}`} style={{ fontSize: "0.68rem" }}>
                          {reason}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </details>
      ) : null}

      {trace.reasons.length > 0 ? (
        <div>
          <div style={labelStyle}>Why</div>
          <ul style={{ color: "var(--parchment)", margin: "0.3rem 0 0", paddingLeft: "1.1rem" }}>
            {trace.reasons.map((reason, idx) => (
              <li key={`${idx}-${reason}`} style={{ fontSize: "0.74rem" }}>
                {reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {prose ? (
        <div
          data-decision-prose="true"
          style={{
            borderTop: "1px dashed rgba(232, 225, 211, 0.16)",
            paddingTop: "0.55rem",
          }}
        >
          <div style={labelStyle}>Narrative summary (generated from trace)</div>
          <p style={{ color: "var(--parchment)", fontSize: "0.78rem", margin: "0.25rem 0 0" }}>
            {prose}
          </p>
        </div>
      ) : null}
    </div>
  );
}
