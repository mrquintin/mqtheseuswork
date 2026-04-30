import { getPortfolioSummary } from "@/lib/forecastsApi";
import type { PortfolioSummary } from "@/lib/forecastsTypes";

type PublicTradingPosture = "DISABLED" | "ENABLED";

type PortfolioSummaryLike = PortfolioSummary & {
  liveTradingEnabled?: boolean;
  liveTradingStatus?: string | null;
  live_trading_enabled?: boolean;
  live_trading_status?: string | null;
};

function optionalBool(...values: Array<boolean | null | undefined>): boolean | undefined {
  for (const value of values) {
    if (typeof value === "boolean") return value;
  }
  return undefined;
}

function optionalString(...values: Array<string | null | undefined>): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

export function liveTradingPostureFor(
  summary: PortfolioSummaryLike | null,
): PublicTradingPosture {
  const explicit = optionalString(
    summary?.liveTradingStatus,
    summary?.live_trading_status,
  )?.toUpperCase();

  if (explicit?.startsWith("ENABLED")) return "ENABLED";
  if (explicit === "DISABLED") return "DISABLED";

  return optionalBool(
    summary?.liveTradingEnabled,
    summary?.live_trading_enabled,
  )
    ? "ENABLED"
    : "DISABLED";
}

export default async function TransparencyFooter() {
  let summary: PortfolioSummaryLike | null = null;

  try {
    summary = await getPortfolioSummary();
  } catch (error) {
    console.error("homepage_portfolio_summary_failed", error);
  }

  const posture = liveTradingPostureFor(summary);

  return (
    <footer
      aria-label="Public transparency note"
      style={{
        borderTop: "1px solid rgba(232, 225, 211, 0.14)",
        color: "var(--parchment-dim)",
        fontSize: "0.82rem",
        fontStyle: "italic",
        lineHeight: 1.6,
        marginTop: "2.25rem",
        paddingTop: "1rem",
      }}
    >
      <p style={{ margin: 0 }}>
        Predictions are model-generated, source-grounded, and not financial
        advice. Live trading:{" "}
        <span
          className="mono"
          data-live-trading-posture={posture}
          style={{
            color:
              posture === "ENABLED"
                ? "var(--forecasts-prob-yes)"
                : "var(--parchment-dim)",
            fontStyle: "normal",
            letterSpacing: "0.08em",
          }}
        >
          {posture}
        </span>
      </p>
    </footer>
  );
}
