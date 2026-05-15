/**
 * Shared types for the unified portfolio surface. Mirrors the
 * `UnifiedPortfolioOverview` and `EquityPortfolioSurface` Pydantic
 * models served by current_events_api.
 */

export type LivePillState = "DISABLED" | "ENABLED-AWAITING-AUTH" | "ENABLED";

export type LiveStatusPills = {
  forecasts: LivePillState;
  equities: LivePillState;
};

export type TrackTotals = {
  openPositions: number;
  realizedPaperPnlUsd: number;
  unrealizedPaperPnlUsd: number;
};

export type ActivePrinciple = {
  conclusionId: string;
  snippet: string;
  weight: number;
  positionCount: number;
};

export type NetPnlPoint = {
  ts: string;
  paperBalanceUsd: number;
  paperPnlUsd: number;
};

export type UnifiedOverview = {
  organizationId: string;
  netPaperPnlUsd: number;
  netPaperPnlCurve: NetPnlPoint[];
  forecasts: TrackTotals;
  equities: TrackTotals;
  killSwitchEngaged: boolean;
  killSwitchReason: string | null;
  liveStatus: LiveStatusPills;
  activePrinciples: ActivePrinciple[];
};

export type EquityOpenPosition = {
  positionId: string;
  signalId: string;
  instrumentSymbol: string;
  instrumentName: string | null;
  side: string;
  qty: number;
  entryPrice: number;
  entryAt: string;
  unrealizedPnlUsd: number | null;
  horizonDays: number | null;
  direction: string;
  lastUpdated: string;
};

export type EquityRecentSignal = {
  signalId: string;
  instrumentSymbol: string;
  direction: string;
  headline: string;
  confidenceLow: number;
  confidenceHigh: number;
  targetPriceLow: number | null;
  targetPriceHigh: number | null;
  horizonDays: number;
  status: string;
  createdAt: string;
};

export type EquityCurvePoint = {
  ts: string;
  paperPnlUsd: number;
};

export type MapeBucket = {
  horizonLabel: string;
  n: number;
  meanAbsolutePctError: number | null;
};

export type EquitySurface = {
  organizationId: string;
  paperBalanceUsd: number;
  totals: TrackTotals;
  liveStatus: LiveStatusPills;
  killSwitchEngaged: boolean;
  killSwitchReason: string | null;
  openPositions: EquityOpenPosition[];
  recentSignals: EquityRecentSignal[];
  paperPnlCurve: EquityCurvePoint[];
  targetPriceMape: MapeBucket[];
};

export type DecisionTrace = {
  kind: "forecast" | "equity";
  positionId: string;
  marketOrInstrumentTitle: string;
  principles: {
    conclusionId: string;
    snippet: string;
    weight: number | null;
  }[];
  citations: {
    sourceType: string;
    sourceId: string;
    quotedSpan: string;
    supportLabel: string | null;
  }[];
  signal:
    | {
        id: string;
        headline: string;
        directionOrSide: string;
        rationale: string | null;
        confidenceLow: number | null;
        confidenceHigh: number | null;
      }
    | null;
  position: {
    id: string;
    mode: string;
    side: string;
    size: number;
    entryPrice: number;
    status: string;
    createdAt: string;
  };
  fill:
    | {
        exitPrice: number | null;
        exitAt: string | null;
        realizedPnlUsd: number | null;
      }
    | null;
  resolution:
    | {
        outcome: string | null;
        resolvedAt: string | null;
        brierScore: number | null;
        justification: string | null;
      }
    | null;
  gates: {
    gateName: string;
    passed: boolean;
    reason: string;
  }[];
};
