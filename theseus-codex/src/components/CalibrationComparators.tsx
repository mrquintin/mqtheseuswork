import { HEADLINE_MIN_N, type HeadlineBrier } from "@/lib/calibrationData";

/**
 * "What this means" — the comparator panel.
 *
 * A Brier score in isolation is close to meaningless: "0.18" tells a
 * reader nothing until they know what is trivial to beat. This section
 * pins the firm's headline against three reference forecasters:
 *
 *   (a) random guessing            → Brier 0.25 by construction
 *   (b) always forecasting 50%     → also 0.25
 *   (c) climatology (always the
 *       historical base rate p̄)   → p̄·(1 − p̄), the real bar to clear
 *
 * The firm's own number is shown only when the headline is `stable`
 * (n ≥ HEADLINE_MIN_N); otherwise its row says the figure is withheld,
 * matching the headline's discipline.
 */

const RANDOM_BRIER = 0.25;
/** Bars are scaled against this max so 0.25 sits well inside the frame. */
const SCALE_MAX = 0.3;

type ComparatorRow = {
  key: string;
  label: string;
  value: number | null;
  note: string;
  firm?: boolean;
};

function fmt(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return value.toFixed(3);
}

export default function CalibrationComparators({
  headline,
  outcomeBaseRate,
}: {
  headline: HeadlineBrier;
  outcomeBaseRate: number | null;
}) {
  const climatology =
    outcomeBaseRate !== null ? outcomeBaseRate * (1 - outcomeBaseRate) : null;

  const rows: ComparatorRow[] = [
    {
      key: "random",
      label: "Random guessing",
      value: RANDOM_BRIER,
      note: "Uniform-random probabilities. Lands at 0.25 by construction — the noise floor.",
    },
    {
      key: "fifty",
      label: "Always forecast 50%",
      value: RANDOM_BRIER,
      note: "0.50 on every market. Also 0.25 — refusing to commit is not skill, just a different way to score the floor.",
    },
    {
      key: "climatology",
      label:
        outcomeBaseRate !== null
          ? `Climatology — always ${(outcomeBaseRate * 100).toFixed(0)}%`
          : "Climatology — historical base rate",
      value: climatology,
      note:
        outcomeBaseRate !== null
          ? `Forecast the historical YES base rate (p̄ = ${outcomeBaseRate.toFixed(2)}) on every market. Brier = p̄·(1 − p̄). This — not 0.25 — is the bar a real forecaster has to clear.`
          : "Forecast the historical YES base rate on every market. Needs resolved outcomes to compute.",
    },
    {
      key: "firm",
      label: "Theseus (this scorecard)",
      value: headline.stable ? headline.meanBrier : null,
      note: headline.stable
        ? `The firm's all-time Brier over n = ${headline.n} resolved forecasts. Compare it to the rows above — beating 0.25 is table stakes; beating climatology is the claim worth making.`
        : `Withheld — n = ${headline.n} is below the ${HEADLINE_MIN_N}-resolution floor for a stable score. The comparators stand on their own; the firm's number does not yet.`,
      firm: true,
    },
  ];

  return (
    <section
      style={{ marginBottom: "2rem" }}
      aria-labelledby="comparators-title"
    >
      <h2
        id="comparators-title"
        style={{
          fontSize: "0.92rem",
          letterSpacing: "0.18em",
          textTransform: "uppercase",
        }}
      >
        What this means
      </h2>
      <p style={{ fontSize: "0.85rem", marginTop: "0.4rem", lineHeight: 1.55 }}>
        A Brier score on its own is not interpretable. The number only earns
        meaning against what is easy to beat: a coin-flipper and a
        permanent-50% forecaster both score <strong>0.25</strong>, and a
        forecaster who just repeats the base rate scores{" "}
        <strong>{fmt(climatology)}</strong>. Read the firm's headline against
        these, not in isolation.
      </p>
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: "0.9rem 0 0",
          display: "grid",
          gap: "0.55rem",
        }}
      >
        {rows.map((row) => {
          const pct =
            row.value === null
              ? 0
              : Math.min(100, (row.value / SCALE_MAX) * 100);
          return (
            <li
              key={row.key}
              style={{
                border: `1px solid ${row.firm ? "#d4a017" : "#d8d4cb"}`,
                background: row.firm ? "#fffbeb" : "#fffdf7",
                padding: "0.6rem 0.8rem",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "0.75rem",
                  alignItems: "baseline",
                  flexWrap: "wrap",
                }}
              >
                <strong style={{ fontWeight: row.firm ? 600 : 500, fontSize: "0.86rem" }}>
                  {row.label}
                </strong>
                <span
                  style={{
                    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                    fontSize: "0.95rem",
                    color: row.firm ? "#7a5b0d" : "#3a342a",
                  }}
                >
                  Brier {fmt(row.value)}
                </span>
              </div>
              <div
                aria-hidden="true"
                style={{
                  marginTop: "0.4rem",
                  height: "6px",
                  background: "#ece8de",
                  borderRadius: "3px",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${pct}%`,
                    height: "100%",
                    background: row.firm ? "#d4a017" : "#a39a86",
                  }}
                />
              </div>
              <p
                style={{
                  margin: "0.4rem 0 0",
                  fontSize: "0.76rem",
                  color: "#4b4234",
                  lineHeight: 1.5,
                }}
              >
                {row.note}
              </p>
            </li>
          );
        })}
      </ul>
      <p
        style={{
          marginTop: "0.6rem",
          fontSize: "0.72rem",
          color: "#5a4e3a",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        }}
      >
        Lower is better. Bars scaled to a {SCALE_MAX.toFixed(2)} maximum.
        Climatology Brier = p̄·(1 − p̄) over the resolved set; a per-market
        prior comparator needs the market-price snapshot at publish time,
        which is not in the public manifest.
      </p>
    </section>
  );
}
