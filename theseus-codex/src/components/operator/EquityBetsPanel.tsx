import type { ReactNode } from "react";

export type EquityBetsPanelProps = {
  liveTradingEnabled: boolean;
  primaryBroker: "ALPACA" | "ROBINHOOD" | string;
  robinhoodEnabled: boolean;
  alpacaConfigured: boolean;
  maxStakeUsd: number | null;
  maxDailyLossUsd: number | null;
  liveBalanceUsd: number | null;
};

/**
 * Founder-only "Equity bets" panel for the forecasts operator console.
 *
 * Mirrors the prediction-market panels: it summarises the live equity track
 * (Alpaca recommended, Robinhood optional) and renders an explicit yellow
 * risk banner whenever the Robinhood adapter is enabled, naming the ToS /
 * stability caveats so the operator cannot miss them.
 */
export default function EquityBetsPanel({
  liveTradingEnabled,
  primaryBroker,
  robinhoodEnabled,
  alpacaConfigured,
  maxStakeUsd,
  maxDailyLossUsd,
  liveBalanceUsd,
}: EquityBetsPanelProps) {
  const broker = (primaryBroker || "ALPACA").toUpperCase();
  const usingRobinhood = robinhoodEnabled || broker === "ROBINHOOD";

  return (
    <section
      aria-labelledby="op-equity-bets"
      data-testid="operator-equity-bets-panel"
      style={{
        border: "1px solid rgba(205, 151, 67, 0.45)",
        borderRadius: 6,
        display: "grid",
        gap: "0.7rem",
        padding: "0.9rem 1rem",
      }}
    >
      <header style={{ display: "grid", gap: "0.2rem" }}>
        <h2
          id="op-equity-bets"
          style={{
            color: "var(--amber)",
            fontFamily: "'Cinzel', serif",
            fontSize: "1.05rem",
            letterSpacing: "0.06em",
            margin: 0,
          }}
        >
          Equity bets
        </h2>
        <p
          className="mono"
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.66rem",
            letterSpacing: "0.1em",
            margin: 0,
          }}
        >
          live cash-account equity orders — same eight-gate safety contract as
          prediction-market live bets
        </p>
      </header>

      {usingRobinhood ? <RobinhoodRiskBanner /> : null}

      <dl
        style={{
          columnGap: "1.2rem",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
          margin: 0,
          rowGap: "0.55rem",
        }}
      >
        <Stat
          label="Live equity trading"
          value={liveTradingEnabled ? "ENABLED" : "OFF"}
          good={liveTradingEnabled === false}
        />
        <Stat label="Primary broker" value={broker} />
        <Stat
          label="Alpaca credentials"
          value={alpacaConfigured ? "CONFIGURED" : "MISSING"}
          good={alpacaConfigured}
        />
        <Stat
          label="Robinhood adapter"
          value={robinhoodEnabled ? "ENABLED" : "OFF"}
          good={!robinhoodEnabled}
        />
        <Stat
          label="Max per-order stake"
          value={fmtUsd(maxStakeUsd, "FORECASTS_MAX_STAKE_USD")}
        />
        <Stat
          label="Max daily loss"
          value={fmtUsd(maxDailyLossUsd, "FORECASTS_MAX_DAILY_LOSS_USD")}
        />
        <Stat label="Live cash" value={fmtUsd(liveBalanceUsd, "—")} />
      </dl>
    </section>
  );
}

function RobinhoodRiskBanner() {
  return (
    <div
      role="alert"
      data-testid="operator-robinhood-risk-banner"
      style={{
        background: "rgba(205, 151, 67, 0.14)",
        border: "1px solid rgba(205, 151, 67, 0.7)",
        borderRadius: 4,
        color: "var(--amber)",
        display: "grid",
        gap: "0.25rem",
        padding: "0.7rem 0.85rem",
      }}
    >
      <strong style={{ fontFamily: "'Cinzel', serif", letterSpacing: "0.04em" }}>
        Robinhood adapter is unofficial.
      </strong>
      <span style={{ color: "var(--parchment)", fontSize: "0.82rem", lineHeight: 1.45 }}>
        Automation may violate Robinhood ToS. Use at your own risk. Robinhood
        does not publish a supported public retail trading API; this adapter
        depends on the reverse-engineered <code>robin_stocks</code> library
        which Robinhood periodically breaks. The eight-gate safety contract
        still applies — flipping this on is not a bypass.
      </span>
    </div>
  );
}

function Stat({
  label,
  value,
  good,
}: {
  label: string;
  value: ReactNode;
  good?: boolean;
}) {
  const tone =
    good === undefined
      ? "var(--parchment)"
      : good
        ? "var(--success, #7ea83a)"
        : "var(--ember, #b95c5c)";
  return (
    <div style={{ display: "grid", gap: "0.15rem" }}>
      <dt
        className="mono"
        style={{
          color: "var(--parchment-dim)",
          fontSize: "0.62rem",
          letterSpacing: "0.12em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </dt>
      <dd style={{ color: tone, fontFamily: "'IBM Plex Mono', monospace", margin: 0 }}>
        {value}
      </dd>
    </div>
  );
}

function fmtUsd(value: number | null, placeholder: string): string {
  if (value === null || !Number.isFinite(value)) return placeholder;
  return `$${value.toFixed(2)}`;
}
