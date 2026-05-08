import type { MethodDriftSummary, MethodDriftEvent } from "@/lib/api/round3";

const SEVERITY_COLOR: Record<string, string> = {
  escalate: "var(--ember, #c0392b)",
  warn: "var(--amber, #d4a017)",
  insufficient: "var(--parchment-dim)",
  ok: "var(--parchment-dim)",
  unknown: "var(--parchment-dim)",
};

const SEVERITY_LABEL: Record<string, string> = {
  escalate: "ESCALATE",
  warn: "WARN",
  insufficient: "INSUFFICIENT (n<8)",
  ok: "STABLE",
  unknown: "—",
};

function fmt(n: number | null, digits = 2): string {
  return n == null ? "—" : n.toFixed(digits);
}

function fmtP(n: number | null): string {
  if (n == null) return "—";
  return n < 0.001 ? "<0.001" : n.toFixed(3);
}

/**
 * Operator drift surface for one method. Shows the current alert state
 * (after hysteresis), the calibration trend across recent windows, and
 * the alert ledger so a reviewer can audit when each transition fired.
 *
 * The trend "chart" is rendered as a sparkline of slope vs. window
 * end-date using inline SVG; we deliberately do NOT pull in a charting
 * library for this — the Codex's data tables are the canonical surface
 * and a 60-line sparkline is the right shape for the operator panel.
 */
export default function DriftPanel({
  methodName,
  summary,
}: {
  methodName: string;
  summary: MethodDriftSummary;
}) {
  const events = summary.events; // most-recent first
  const slopeEvents = events
    .filter((e) => e.calibrationSlope != null && !Number.isNaN(e.calibrationSlope))
    .slice(0, 12)
    .reverse(); // oldest → newest for chart layout

  const banner = SEVERITY_COLOR[summary.state] ?? "var(--parchment-dim)";
  const active =
    summary.state === "warn" || summary.state === "escalate";

  return (
    <div
      className="portal-card"
      style={{
        padding: "1.25rem",
        marginBottom: "1.5rem",
        borderLeft: active ? `3px solid ${banner}` : undefined,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: "0.5rem",
        }}
      >
        <div
          style={{
            fontSize: "0.6rem",
            color: "var(--gold-dim)",
            textTransform: "uppercase",
            letterSpacing: "0.1em",
          }}
        >
          Drift — {methodName}
        </div>
        <div
          style={{
            fontSize: "0.65rem",
            letterSpacing: "0.08em",
            color: banner,
            fontWeight: active ? 600 : 400,
          }}
        >
          {SEVERITY_LABEL[summary.state] ?? "—"}
        </div>
      </div>

      {events.length === 0 ? (
        <p style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", margin: 0 }}>
          No drift evaluation yet. The nightly scheduler runs{" "}
          <code style={{ color: "var(--parchment)" }}>
            noosphere.evaluation.scheduler_drift
          </code>
          ; this panel will populate after the first window completes
          (n ≥ 8 resolutions required).
        </p>
      ) : (
        <>
          <p style={{ color: "var(--parchment-dim)", fontSize: "0.75rem", margin: "0 0 0.75rem" }}>
            {summary.lastActiveAt
              ? `Last active alert observed ${summary.lastActiveAt.slice(0, 10)}.`
              : "No alert has fired in the recorded window."}
          </p>

          {slopeEvents.length >= 2 && (
            <DriftSparkline events={slopeEvents} />
          )}

          <div
            style={{
              fontSize: "0.6rem",
              color: "var(--gold-dim)",
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              margin: "0.75rem 0 0.4rem",
            }}
          >
            Alert history
          </div>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "0.78rem",
              color: "var(--parchment)",
            }}
          >
            <thead>
              <tr style={{ color: "var(--gold-dim)", textAlign: "left" }}>
                <th style={{ padding: "0.25rem 0.5rem 0.25rem 0", fontWeight: 400 }}>When</th>
                <th style={{ padding: "0.25rem 0.5rem", fontWeight: 400 }}>Window</th>
                <th style={{ padding: "0.25rem 0.5rem", fontWeight: 400 }}>n</th>
                <th style={{ padding: "0.25rem 0.5rem", fontWeight: 400 }}>Slope</th>
                <th style={{ padding: "0.25rem 0.5rem", fontWeight: 400 }}>Baseline</th>
                <th style={{ padding: "0.25rem 0.5rem", fontWeight: 400 }}>σ</th>
                <th style={{ padding: "0.25rem 0.5rem", fontWeight: 400 }}>p</th>
                <th style={{ padding: "0.25rem 0.5rem", fontWeight: 400 }}>Severity</th>
              </tr>
            </thead>
            <tbody>
              {events.slice(0, 30).map((ev) => (
                <tr key={ev.id} style={{ borderTop: "1px solid var(--gold-dim)" }}>
                  <td style={{ padding: "0.35rem 0.5rem 0.35rem 0" }}>
                    {ev.observedAt.slice(0, 10)}
                  </td>
                  <td style={{ padding: "0.35rem 0.5rem" }}>{ev.windowDays}d</td>
                  <td style={{ padding: "0.35rem 0.5rem" }}>{ev.sampleSize}</td>
                  <td style={{ padding: "0.35rem 0.5rem" }}>{fmt(ev.calibrationSlope)}</td>
                  <td style={{ padding: "0.35rem 0.5rem" }}>{fmt(ev.baselineSlope)}</td>
                  <td style={{ padding: "0.35rem 0.5rem" }}>{fmt(ev.sigma)}</td>
                  <td style={{ padding: "0.35rem 0.5rem" }}>{fmtP(ev.pValue)}</td>
                  <td
                    style={{
                      padding: "0.35rem 0.5rem",
                      color: SEVERITY_COLOR[ev.severity] ?? "var(--parchment)",
                      fontWeight:
                        ev.severity === "warn" || ev.severity === "escalate"
                          ? 600
                          : 400,
                      textTransform: "uppercase",
                      fontSize: "0.65rem",
                      letterSpacing: "0.08em",
                    }}
                  >
                    {ev.severity}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ color: "var(--parchment-dim)", fontSize: "0.65rem", marginTop: "0.5rem" }}>
            Hysteresis: alert clears after two consecutive clean windows.
            Permutation seed and p-value are recorded with each event so
            the test is exactly reproducible from the audit blob.
          </p>
        </>
      )}
    </div>
  );
}

function DriftSparkline({ events }: { events: MethodDriftEvent[] }) {
  const slopes = events.map((e) => e.calibrationSlope as number);
  const baselines = events.map((e) =>
    e.baselineSlope == null ? null : (e.baselineSlope as number),
  );
  const all = [
    ...slopes,
    ...baselines.filter((b): b is number => b != null),
  ];
  const lo = Math.min(0, Math.min(...all));
  const hi = Math.max(1.2, Math.max(...all));
  const span = hi - lo || 1;

  const W = 480;
  const H = 80;
  const pad = 4;

  function x(i: number): number {
    if (events.length === 1) return W / 2;
    return pad + ((W - 2 * pad) * i) / (events.length - 1);
  }
  function y(v: number): number {
    return H - pad - ((v - lo) / span) * (H - 2 * pad);
  }

  const slopePath = slopes
    .map((v, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`)
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height={H}
      role="img"
      aria-label="Calibration slope over recent drift windows"
      style={{ display: "block", marginTop: "0.25rem" }}
    >
      <line
        x1={pad}
        x2={W - pad}
        y1={y(1.0)}
        y2={y(1.0)}
        stroke="var(--gold-dim, #8a7a3a)"
        strokeDasharray="2 3"
        strokeWidth={1}
      />
      <path
        d={slopePath}
        fill="none"
        stroke="var(--gold, #d4a017)"
        strokeWidth={1.5}
      />
      {events.map((ev, i) => (
        <circle
          key={ev.id}
          cx={x(i)}
          cy={y(slopes[i])}
          r={2.5}
          fill={SEVERITY_COLOR[ev.severity] ?? "var(--gold)"}
        />
      ))}
    </svg>
  );
}
