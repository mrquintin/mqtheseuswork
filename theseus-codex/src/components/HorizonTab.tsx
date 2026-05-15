import Link from "next/link";

import type {
  HorizonBucketCalibration,
  HorizonCalibration,
  MethodHorizonCell,
} from "@/lib/calibrationData";

/**
 * "Horizon" tab of the public calibration scorecard.
 *
 * A single Brier hides the fact that a 7-day forecast and a 1-year
 * forecast are different animals. This tab slices calibration by
 * time-to-resolution, shows the per-bucket reliability with bootstrap
 * CIs, names the firm's empirically *useful prediction horizon*, and
 * spells out the implication for new forecasts.
 *
 * Honesty is structural, not editorial:
 *   - buckets below the firm's display threshold (n < minBucketN) show a
 *     sample size and nothing modelled — no slope, no CI, no verdict;
 *   - the useful-horizon ceiling is whatever the numbers say, including
 *     "0 days" — bad numbers are surfaced, never smoothed;
 *   - every bucket carries its own note explaining its verdict.
 *
 * Pure server component — all estimation happens upstream in
 * `loadHorizonCalibration` (Python `horizon_calibration` is the canonical
 * estimator); this file only renders.
 */

const BORDER = "#d8d4cb";
const CARD_BG = "#fffdf7";
const MUTED = "#7a6d55";
const INK = "#3a342a";
const WARN_BORDER = "#d4a017";
const WARN_BG = "#fffbeb";
const WARN_INK = "#7a5b0d";
const GOOD = "#1f6f3a";
const BAD = "#a52a2a";
const MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";

function fmt(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

function ci(low: number | null, high: number | null, digits = 3): string {
  if (low === null || high === null) return "—";
  return `[${low.toFixed(digits)}, ${high.toFixed(digits)}]`;
}

export default function HorizonTab({ horizon }: { horizon: HorizonCalibration }) {
  return (
    <section aria-labelledby="horizon-tab-title">
      <TabNav />
      <Hero horizon={horizon} />
      <UsefulHorizonCallout horizon={horizon} />
      <BucketTable horizon={horizon} />
      <Implication horizon={horizon} />
      <MethodHorizonTable horizon={horizon} />
      <Footnotes horizon={horizon} />
    </section>
  );
}

function TabNav() {
  const tabStyle = (active: boolean): React.CSSProperties => ({
    padding: "0.4rem 0.9rem",
    border: `1px solid ${active ? WARN_BORDER : BORDER}`,
    background: active ? WARN_BG : "#ffffff",
    color: active ? WARN_INK : INK,
    fontFamily: MONO,
    fontSize: "0.8rem",
    textDecoration: "none",
  });
  return (
    <nav
      aria-label="Calibration scorecard sections"
      style={{ display: "flex", gap: "0.4rem", marginBottom: "1.5rem" }}
    >
      <Link href="/calibration" style={tabStyle(false)}>
        Overview
      </Link>
      <Link href="/calibration/horizon" aria-current="page" style={tabStyle(true)}>
        Horizon
      </Link>
    </nav>
  );
}

function Hero({ horizon }: { horizon: HorizonCalibration }) {
  return (
    <header style={{ marginBottom: "1.75rem" }}>
      <h1 id="horizon-tab-title" className="public-title" style={{ fontSize: "2rem" }}>
        Calibration by forecast horizon
      </h1>
      <p className="public-lede" style={{ marginTop: "0.5rem" }}>
        A 7-day forecast and a 1-year forecast are different animals. A
        single headline Brier hides that. Below, every resolved forecast is
        bucketed by its <strong>horizon</strong> — the time between
        publishing it and the market resolving — and scored on its own.
        &ldquo;Beats chance&rdquo; means the bucket&rsquo;s bootstrap Brier
        CI sits entirely below {fmt(horizon.chanceBrier, 2)} (random /
        always-50%).
      </p>
      <p style={{ marginTop: "0.7rem", fontFamily: MONO, fontSize: "0.76rem", color: "#5a5247" }}>
        n_resolved={horizon.nTotal} · bins={horizon.buckets.length} ·
        min_bucket_n={horizon.minBucketN} · source={horizon.source} ·
        schema={horizon.schema}
      </p>
    </header>
  );
}

function UsefulHorizonCallout({ horizon }: { horizon: HorizonCalibration }) {
  const uh = horizon.usefulHorizon;
  const noDecay = uh.beatsChanceAtEveryHorizon;
  const noHorizon = !noDecay && uh.horizonDays === null;
  const headline = noDecay
    ? "No decay observed"
    : noHorizon
      ? "No useful horizon established"
      : `Useful prediction horizon: ${uh.horizonLabel}`;
  const tone = noDecay ? GOOD : noHorizon ? BAD : WARN_INK;
  const border = noDecay ? "#bcd9be" : noHorizon ? "#e0b4b4" : WARN_BORDER;
  const bg = noDecay ? "#f5faf2" : noHorizon ? "#fdf3f3" : WARN_BG;
  return (
    <section
      style={{
        border: `1px solid ${border}`,
        background: bg,
        padding: "1rem 1.15rem",
        marginBottom: "1.75rem",
      }}
      aria-labelledby="useful-horizon-label"
    >
      <div
        id="useful-horizon-label"
        style={{
          fontSize: "0.68rem",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: MUTED,
        }}
      >
        Decay analysis
      </div>
      <div
        style={{
          fontFamily: MONO,
          fontSize: "1.5rem",
          lineHeight: 1.2,
          marginTop: "0.25rem",
          color: tone,
        }}
      >
        {headline}
      </div>
      <p style={{ fontSize: "0.84rem", color: "#5a5247", marginTop: "0.5rem", marginBottom: 0, lineHeight: 1.55 }}>
        {uh.rationale}
      </p>
      {uh.limitingBucketKey ? (
        <p
          style={{
            fontFamily: MONO,
            fontSize: "0.74rem",
            color: MUTED,
            marginTop: "0.4rem",
            marginBottom: 0,
          }}
        >
          limiting bucket: {uh.limitingBucketKey}
        </p>
      ) : null}
    </section>
  );
}

function bucketVerdict(b: HorizonBucketCalibration): { label: string; color: string } {
  // The bucket's own note is authoritative — it encodes the n-threshold
  // and the bootstrap-CI verdict in one place.
  if (b.n === 0) return { label: "no data", color: MUTED };
  if (b.note.includes("sample size only")) return { label: "n only", color: MUTED };
  if (b.beatsChance) return { label: "beats chance", color: GOOD };
  return { label: "≈ chance", color: BAD };
}

function BucketTable({ horizon }: { horizon: HorizonCalibration }) {
  return (
    <section style={{ marginBottom: "2rem" }} aria-labelledby="horizon-buckets-title">
      <h2
        id="horizon-buckets-title"
        style={{ fontSize: "0.92rem", letterSpacing: "0.18em", textTransform: "uppercase" }}
      >
        Per-bucket reliability
      </h2>
      <p style={{ fontSize: "0.83rem", marginTop: "0.4rem", color: "#5a5247", lineHeight: 1.55 }}>
        Mean Brier with a non-parametric bootstrap CI, the calibration slope
        (OLS of outcome ~ probability; ≈ 1.0 is well-discriminated), and the
        bucket&rsquo;s own base rate. Below n={horizon.minBucketN} we print
        the sample size and nothing else — a slope over a handful of points
        is noise.
      </p>
      <div style={{ overflowX: "auto" }}>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "0.78rem",
            marginTop: "0.6rem",
          }}
        >
          <thead>
            <tr style={{ textAlign: "left", color: MUTED }}>
              <th style={{ padding: "0.35rem 0.5rem 0.35rem 0" }}>Horizon</th>
              <th style={{ padding: "0.35rem 0.5rem" }}>n</th>
              <th style={{ padding: "0.35rem 0.5rem" }}>Mean Brier</th>
              <th style={{ padding: "0.35rem 0.5rem" }}>Brier CI</th>
              <th style={{ padding: "0.35rem 0.5rem" }}>Slope</th>
              <th style={{ padding: "0.35rem 0.5rem" }}>Slope CI</th>
              <th style={{ padding: "0.35rem 0.5rem" }}>Base rate</th>
              <th style={{ padding: "0.35rem 0.5rem" }}>Verdict</th>
            </tr>
          </thead>
          <tbody style={{ fontFamily: MONO }}>
            {horizon.buckets.map((b) => {
              const verdict = bucketVerdict(b);
              return (
                <tr key={b.key} style={{ borderTop: `1px solid #ece8de` }}>
                  <td style={{ padding: "0.4rem 0.5rem 0.4rem 0", color: INK }}>{b.label}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{b.n}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{fmt(b.meanBrier)}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>
                    {ci(b.brierCiLow, b.brierCiHigh)}
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{fmt(b.slope, 2)}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>
                    {ci(b.slopeCiLow, b.slopeCiHigh, 2)}
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{fmt(b.baseRate, 2)}</td>
                  <td style={{ padding: "0.4rem 0.5rem", color: verdict.color }}>
                    {verdict.label}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: "0.7rem 0 0",
          fontSize: "0.74rem",
          color: MUTED,
        }}
      >
        {horizon.buckets
          .filter((b) => b.n > 0)
          .map((b) => (
            <li key={b.key} style={{ padding: "0.12rem 0" }}>
              <span style={{ fontFamily: MONO, color: INK }}>{b.label}</span> — {b.note}
            </li>
          ))}
      </ul>
    </section>
  );
}

function Implication({ horizon }: { horizon: HorizonCalibration }) {
  const uh = horizon.usefulHorizon;
  let body: React.ReactNode;
  if (uh.beatsChanceAtEveryHorizon) {
    body = (
      <>
        Calibration beats chance at every measured horizon. New forecasts
        carry no horizon caveat on the strength of this record — but the
        longest bucket is still the thinnest evidence, so the warning will
        re-arm the moment a long-horizon bucket slips.
      </>
    );
  } else if (uh.horizonDays === null) {
    body = (
      <>
        The firm has not yet established a useful horizon at any range —
        there is not enough resolved data to claim signal. Until that
        changes, <strong>every</strong> new forecast is issued with the
        explicit &ldquo;low confidence&rdquo; framing, regardless of
        horizon.
      </>
    );
  } else {
    body = (
      <>
        Below <strong>{uh.horizonLabel}</strong>, the firm is contributing
        real signal — its forecasts in that range beat chance. Beyond it,
        calibration is not distinguishable from a coin flip, so a forecast
        issued past {uh.horizonLabel} must carry the explicit{" "}
        <em>&ldquo;low confidence, long horizon&rdquo;</em> framing. The
        new-forecast form surfaces a soft warning at that threshold — see
        the founder console.
      </>
    );
  }
  return (
    <section
      style={{
        border: `1px solid ${BORDER}`,
        background: CARD_BG,
        padding: "1rem 1.15rem",
        marginBottom: "2rem",
      }}
      aria-labelledby="horizon-implication-title"
    >
      <h2
        id="horizon-implication-title"
        style={{ fontSize: "0.92rem", letterSpacing: "0.18em", textTransform: "uppercase", margin: 0 }}
      >
        Implication for new forecasts
      </h2>
      <p style={{ fontSize: "0.86rem", marginTop: "0.5rem", marginBottom: 0, lineHeight: 1.6 }}>
        {body}
      </p>
    </section>
  );
}

function MethodHorizonTable({ horizon }: { horizon: HorizonCalibration }) {
  const cells = horizon.methodHorizon;
  return (
    <section style={{ marginBottom: "2rem" }} aria-labelledby="method-horizon-title">
      <h2
        id="method-horizon-title"
        style={{ fontSize: "0.92rem", letterSpacing: "0.18em", textTransform: "uppercase" }}
      >
        Method × horizon
      </h2>
      <p style={{ fontSize: "0.83rem", marginTop: "0.4rem", color: "#5a5247", lineHeight: 1.55 }}>
        Some methods calibrate well on short horizons but decay fast on
        long ones. This cross-tab pairs each originating method with the
        horizon bucket its forecasts landed in.
      </p>
      {cells.length === 0 ? (
        <p
          style={{
            fontSize: "0.78rem",
            color: WARN_INK,
            background: WARN_BG,
            border: `1px solid ${WARN_BORDER}`,
            padding: "0.5rem 0.7rem",
            marginTop: "0.5rem",
          }}
        >
          No method × horizon cells. The resolved forecasts in this view
          carry no method→outcome attribution (Round 17 prompt 02 link) —
          this populates once the nightly manifest emits a{" "}
          <code>horizon_calibration</code> block with method linkage.
        </p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "0.78rem",
              marginTop: "0.6rem",
            }}
          >
            <thead>
              <tr style={{ textAlign: "left", color: MUTED }}>
                <th style={{ padding: "0.35rem 0.5rem 0.35rem 0" }}>Method</th>
                <th style={{ padding: "0.35rem 0.5rem" }}>Horizon</th>
                <th style={{ padding: "0.35rem 0.5rem" }}>n</th>
                <th style={{ padding: "0.35rem 0.5rem" }}>Mean Brier</th>
                <th style={{ padding: "0.35rem 0.5rem" }}>Slope</th>
                <th style={{ padding: "0.35rem 0.5rem" }}>Verdict</th>
              </tr>
            </thead>
            <tbody style={{ fontFamily: MONO }}>
              {cells.map((c: MethodHorizonCell) => (
                <tr
                  key={`${c.methodName}@${c.methodVersion}:${c.horizonKey}`}
                  style={{ borderTop: "1px solid #ece8de" }}
                >
                  <td style={{ padding: "0.4rem 0.5rem 0.4rem 0", color: INK }}>
                    {c.methodName}
                    <span style={{ color: MUTED }}> v{c.methodVersion}</span>
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{c.horizonLabel}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{c.n}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{fmt(c.meanBrier)}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{fmt(c.slope, 2)}</td>
                  <td
                    style={{
                      padding: "0.4rem 0.5rem",
                      color: c.beatsChance ? GOOD : c.n < horizon.minBucketN ? MUTED : BAD,
                    }}
                  >
                    {c.n < horizon.minBucketN
                      ? "n only"
                      : c.beatsChance
                        ? "beats chance"
                        : "≈ chance"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Footnotes({ horizon }: { horizon: HorizonCalibration }) {
  if (horizon.notes.length === 0) return null;
  return (
    <section
      style={{ borderTop: "1px solid #ece8de", paddingTop: "1rem" }}
      aria-labelledby="horizon-notes-title"
    >
      <h2
        id="horizon-notes-title"
        style={{
          fontSize: "0.82rem",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: "#5a5247",
        }}
      >
        Notes
      </h2>
      <ul
        style={{
          marginTop: "0.4rem",
          paddingLeft: "1.2rem",
          fontSize: "0.78rem",
          color: "#5a5247",
          lineHeight: 1.55,
        }}
      >
        {horizon.notes.map((note, i) => (
          <li key={i}>{note}</li>
        ))}
      </ul>
    </section>
  );
}
