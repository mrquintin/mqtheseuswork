"use client";

import Link from "next/link";
import { useState, type CSSProperties, type ReactNode } from "react";

import type { BinaryOutcome, DirectionalSample } from "@/lib/calibration";

import DecisionTraceDrawer from "./DecisionTraceDrawer";
import EquitiesTab from "./EquitiesTab";
import OverviewTab from "./OverviewTab";
import type {
  DecisionTrace,
  EquitySurface,
  LivePillState,
  UnifiedOverview,
} from "./types";

type TabId = "overview" | "prediction-markets" | "equities";

export type PortfolioShellProps = {
  overview: UnifiedOverview;
  equitySurface: EquitySurface;
  binaryOutcomes: BinaryOutcome[];
  directionalSamples: DirectionalSample[];
  predictionMarketsContent: ReactNode;
  fetchDecisionTrace?: (
    positionId: string,
    type: "forecast" | "equity",
  ) => Promise<DecisionTrace>;
};

const headerStyle: CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 6,
  background: "rgba(232, 225, 211, 0.04)",
  display: "grid",
  gap: "0.55rem",
  padding: "1rem",
};

const tabBarStyle: CSSProperties = {
  borderBottom: "1px solid rgba(232, 225, 211, 0.14)",
  display: "flex",
  gap: "0.4rem",
  padding: "0 0.4rem",
};

const tabButtonStyle = (active: boolean): CSSProperties => ({
  background: "transparent",
  border: "none",
  borderBottom: active
    ? "2px solid var(--amber)"
    : "2px solid transparent",
  color: active ? "var(--amber)" : "var(--parchment-dim)",
  cursor: "pointer",
  fontFamily: "'Cinzel', serif",
  fontSize: "0.92rem",
  letterSpacing: "0.06em",
  padding: "0.55rem 0.8rem",
});

const pillStyle = (state: LivePillState): CSSProperties => {
  if (state === "DISABLED") {
    return basePill("rgba(180, 175, 165, 0.7)", "rgba(180, 175, 165, 0.35)");
  }
  if (state === "ENABLED-AWAITING-AUTH") {
    return basePill("var(--amber)", "rgba(205, 151, 67, 0.6)");
  }
  return basePill("rgba(127, 196, 143, 0.95)", "rgba(127, 196, 143, 0.5)");
};

function basePill(color: string, border: string): CSSProperties {
  return {
    border: `1px solid ${border}`,
    borderRadius: 999,
    color,
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: "0.62rem",
    letterSpacing: "0.12em",
    padding: "0.2rem 0.55rem",
    textTransform: "uppercase",
  };
}

function fmtUsd(value: number): string {
  const out = new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
    style: "currency",
  }).format(Math.abs(value));
  return value < 0 ? `-${out}` : value > 0 ? `+${out}` : out;
}

export default function PortfolioShell({
  overview,
  equitySurface,
  binaryOutcomes,
  directionalSamples,
  predictionMarketsContent,
  fetchDecisionTrace,
}: PortfolioShellProps) {
  const [tab, setTab] = useState<TabId>("overview");
  const [trace, setTrace] = useState<DecisionTrace | null>(null);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  async function openTrace(
    positionId: string,
    type: "forecast" | "equity",
  ): Promise<void> {
    setDrawerOpen(true);
    setTrace(null);
    setTraceError(null);
    if (!fetchDecisionTrace) {
      setTraceError("Decision-trace endpoint is not wired in this environment.");
      return;
    }
    setTraceLoading(true);
    try {
      const next = await fetchDecisionTrace(positionId, type);
      setTrace(next);
    } catch (err) {
      setTraceError(err instanceof Error ? err.message : "trace lookup failed");
    } finally {
      setTraceLoading(false);
    }
  }

  return (
    <main
      data-testid="portfolio-shell"
      style={{
        display: "grid",
        gap: "1rem",
        margin: "0 auto",
        maxWidth: 1180,
        padding: "1.5rem 1rem 3rem",
      }}
    >
      <HeaderStrip overview={overview} />
      <nav
        aria-label="Portfolio tabs"
        data-testid="portfolio-tabs"
        style={tabBarStyle}
      >
        <TabButton
          active={tab === "overview"}
          id="tab-overview"
          label="Overview"
          onClick={() => setTab("overview")}
        />
        <TabButton
          active={tab === "prediction-markets"}
          id="tab-prediction-markets"
          label="Prediction Markets"
          onClick={() => setTab("prediction-markets")}
        />
        <TabButton
          active={tab === "equities"}
          id="tab-equities"
          label="Equities"
          onClick={() => setTab("equities")}
        />
      </nav>
      <div role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === "overview" ? (
          <OverviewTab
            overview={overview}
            binaryOutcomes={binaryOutcomes}
            directionalSamples={directionalSamples}
          />
        ) : null}
        {tab === "prediction-markets" ? (
          <div data-testid="portfolio-prediction-markets-tab">
            {predictionMarketsContent}
          </div>
        ) : null}
        {tab === "equities" ? (
          <EquitiesTab
            surface={equitySurface}
            onSelectPosition={(positionId) => openTrace(positionId, "equity")}
          />
        ) : null}
      </div>
      {drawerOpen ? (
        <DecisionTraceDrawer
          error={traceError}
          isLoading={traceLoading}
          onClose={() => setDrawerOpen(false)}
          trace={trace}
        />
      ) : null}
    </main>
  );
}

function HeaderStrip({ overview }: { overview: UnifiedOverview }) {
  return (
    <header style={headerStyle} data-testid="portfolio-header-strip">
      <div
        style={{
          alignItems: "baseline",
          display: "flex",
          flexWrap: "wrap",
          gap: "1.2rem",
        }}
      >
        <div>
          <p
            className="mono"
            style={{
              color: "var(--amber-dim)",
              fontSize: "0.6rem",
              letterSpacing: "0.18em",
              margin: 0,
              textTransform: "uppercase",
            }}
          >
            Net firm paper P&amp;L
          </p>
          <strong
            data-testid="portfolio-net-pnl"
            style={{
              // R-022: use the firm palette for P&L.
              color:
                overview.netPaperPnlUsd > 0
                  ? "var(--success)"
                  : overview.netPaperPnlUsd < 0
                    ? "var(--ember)"
                    : "var(--parchment-dim)",
              fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
              fontSize: "1.6rem",
              fontFeatureSettings: '"tnum" 1',
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {fmtUsd(overview.netPaperPnlUsd)}
          </strong>
        </div>
        <div
          style={{
            alignItems: "center",
            display: "flex",
            flexWrap: "wrap",
            gap: "0.5rem",
          }}
        >
          <span style={pillStyle(overview.liveStatus.forecasts)} data-testid="pill-forecasts">
            Forecasts · {overview.liveStatus.forecasts}
          </span>
          <span style={pillStyle(overview.liveStatus.equities)} data-testid="pill-equities">
            Equities · {overview.liveStatus.equities}
          </span>
        </div>
      </div>
      {overview.killSwitchEngaged ? (
        <div
          role="alert"
          data-testid="portfolio-kill-switch-banner"
          style={{
            background: "rgba(172, 54, 37, 0.12)",
            border: "1px solid var(--ember)",
            borderRadius: 4,
            color: "var(--ember)",
            display: "grid",
            gap: "0.15rem",
            padding: "0.5rem 0.7rem",
          }}
        >
          <strong>Kill switch engaged.</strong>
          <span style={{ color: "var(--parchment)", fontSize: "0.82rem" }}>
            {overview.killSwitchReason || "operator-engaged"}
          </span>
          <Link
            href="/forecasts/operator"
            style={{
              color: "var(--amber)",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "0.7rem",
            }}
          >
            Per-track breakdown →
          </Link>
        </div>
      ) : null}
    </header>
  );
}

function TabButton({
  active,
  id,
  label,
  onClick,
}: {
  active: boolean;
  id: string;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-selected={active}
      data-testid={id}
      id={id}
      onClick={onClick}
      role="tab"
      style={tabButtonStyle(active)}
      type="button"
    >
      {label}
    </button>
  );
}
