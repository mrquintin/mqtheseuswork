import type { Metadata } from "next";
import Link from "next/link";

import ForecastPortfolioView from "@/app/(authed)/forecasts/portfolio/ForecastPortfolioView";
import { addWatchedMarket } from "@/app/(authed)/forecasts/portfolio/actions";
import PortfolioShell from "@/components/portfolio/PortfolioShell";
import { db } from "@/lib/db";
import type {
  AdvisoryBetRow,
  EquitySurface,
  LivePillState,
  ScientificBetRow,
  StrategicBetRow,
  UnifiedOverview,
} from "@/components/portfolio/types";
import type { BinaryOutcome, DirectionalSample } from "@/lib/calibration";
import { getForecastPortfolioSurface } from "@/lib/forecastPortfolioData";
import { SITE } from "@/lib/site";
import { requireTenantContext } from "@/lib/tenant";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Theseus — Firm portfolio",
  description:
    "Unified portfolio: prediction-market and equity positions, calibration, kill-switch state, and the principles driving open positions.",
  openGraph: {
    description:
      "Unified portfolio: prediction-market and equity positions, calibration, kill-switch state, and the principles driving open positions.",
    siteName: "Theseus Codex",
    title: "Theseus — Firm portfolio",
    type: "website",
    url: `${SITE}/portfolio`,
  },
};

function pillState(envVar: string, authorized: boolean): LivePillState {
  const enabled = (process.env[envVar] || "").trim().toLowerCase() === "true";
  if (!enabled) return "DISABLED";
  if (!authorized) return "ENABLED-AWAITING-AUTH";
  return "ENABLED";
}

function forecastsAuthorized(): boolean {
  return Boolean(
    (process.env.POLYMARKET_PRIVATE_KEY || "").trim() ||
      (process.env.KALSHI_API_KEY_ID || "").trim(),
  );
}

function equitiesAuthorized(): boolean {
  return Boolean(
    (process.env.ALPACA_API_KEY_ID || process.env.ALPACA_KEY_ID || "").trim() ||
      (process.env.ROBINHOOD_USERNAME || "").trim(),
  );
}

function emptyEquitySurface(organizationId: string): EquitySurface {
  return {
    organizationId,
    paperBalanceUsd: 0,
    totals: {
      openPositions: 0,
      realizedPaperPnlUsd: 0,
      unrealizedPaperPnlUsd: 0,
    },
    liveStatus: {
      forecasts: pillState("FORECASTS_LIVE_TRADING_ENABLED", forecastsAuthorized()),
      equities: pillState("EQUITIES_LIVE_TRADING_ENABLED", equitiesAuthorized()),
    },
    killSwitchEngaged: false,
    killSwitchReason: null,
    openPositions: [],
    recentSignals: [],
    paperPnlCurve: [],
    targetPriceMape: [],
  };
}

type MemoTraceRow = {
  betId: string;
  betKind: "forecast" | "equity";
  mode: string;
  stake: string;
  status: string;
  memoId: string;
  memoTitle: string | null;
  agentId: string | null;
  agentName: string | null;
  outcomeAction: string | null;
  acknowledgedBy: string | null;
  rationale: string | null;
};

async function loadMemoTrace(organizationId: string): Promise<MemoTraceRow[]> {
  // Surface ForecastBet / EquityPosition rows that carry a
  // sourceMemoId, joined to the originating memo and the agent that
  // dispatched it. We deliberately filter to non-null sourceMemoId so
  // pre-prompt-12 bets don't show up — they don't have a memo trace
  // and the "memo trace" surface is meaningless for them.
  const forecastApi = (db as unknown as {
    forecastBet?: {
      findMany: (args: unknown) => Promise<Array<{
        id: string;
        mode: string;
        stakeUsd: { toString: () => string };
        status: string;
        sourceMemoId: string;
      }>>;
    };
  }).forecastBet;
  const equityApi = (db as unknown as {
    equityPosition?: {
      findMany: (args: unknown) => Promise<Array<{
        id: string;
        mode: string;
        qty: { toString: () => string };
        entryPrice: { toString: () => string };
        status: string;
        sourceMemoId: string;
      }>>;
    };
  }).equityPosition;
  const memoApi = (db as unknown as {
    investmentMemo?: {
      findMany: (args: unknown) => Promise<
        Array<{ id: string; title: string }>
      >;
    };
  }).investmentMemo;
  const dispatchApi = (db as unknown as {
    memoDispatch?: {
      findMany: (args: unknown) => Promise<
        Array<{
          memoId: string;
          betLink: string | null;
          agentId: string;
          outcomeAction: string;
          acknowledgedBy: string;
          rationale: string;
        }>
      >;
    };
  }).memoDispatch;
  const agentApi = (db as unknown as {
    portfolioAgent?: {
      findMany: (args: unknown) => Promise<
        Array<{ id: string; name: string }>
      >;
    };
  }).portfolioAgent;

  const out: MemoTraceRow[] = [];
  const forecastBets = forecastApi
    ? await forecastApi
        .findMany({
          where: { organizationId, sourceMemoId: { not: null } },
          orderBy: { createdAt: "desc" },
          take: 100,
          select: {
            id: true,
            mode: true,
            stakeUsd: true,
            status: true,
            sourceMemoId: true,
          },
        })
        .catch(() => [])
    : [];
  const equityPositions = equityApi
    ? await equityApi
        .findMany({
          where: { organizationId, sourceMemoId: { not: null } },
          orderBy: { createdAt: "desc" },
          take: 100,
          select: {
            id: true,
            mode: true,
            qty: true,
            entryPrice: true,
            status: true,
            sourceMemoId: true,
          },
        })
        .catch(() => [])
    : [];
  const memoIds = Array.from(
    new Set([
      ...forecastBets.map((b) => b.sourceMemoId),
      ...equityPositions.map((p) => p.sourceMemoId),
    ]),
  );
  const memos = memoApi && memoIds.length > 0
    ? await memoApi
        .findMany({
          where: { id: { in: memoIds }, organizationId },
          select: { id: true, title: true },
        })
        .catch(() => [])
    : [];
  const memoTitleById = new Map(memos.map((m) => [m.id, m.title]));

  const dispatches = dispatchApi && memoIds.length > 0
    ? await dispatchApi
        .findMany({
          where: {
            organizationId,
            memoId: { in: memoIds },
            betLink: { not: null },
          },
          select: {
            memoId: true,
            betLink: true,
            agentId: true,
            outcomeAction: true,
            acknowledgedBy: true,
            rationale: true,
          },
        })
        .catch(() => [])
    : [];
  const dispatchByBetLink = new Map(
    dispatches.filter((d) => d.betLink).map((d) => [d.betLink!, d]),
  );
  const agentIds = Array.from(
    new Set(dispatches.map((d) => d.agentId)),
  );
  const agents = agentApi && agentIds.length > 0
    ? await agentApi
        .findMany({
          where: { id: { in: agentIds } },
          select: { id: true, name: true },
        })
        .catch(() => [])
    : [];
  const agentNameById = new Map(agents.map((a) => [a.id, a.name]));

  for (const bet of forecastBets) {
    const dispatch = dispatchByBetLink.get(bet.id);
    out.push({
      betId: bet.id,
      betKind: "forecast",
      mode: bet.mode,
      stake: bet.stakeUsd.toString(),
      status: bet.status,
      memoId: bet.sourceMemoId,
      memoTitle: memoTitleById.get(bet.sourceMemoId) ?? null,
      agentId: dispatch?.agentId ?? null,
      agentName: dispatch ? agentNameById.get(dispatch.agentId) ?? null : null,
      outcomeAction: dispatch?.outcomeAction ?? null,
      acknowledgedBy: dispatch?.acknowledgedBy ?? null,
      rationale: dispatch?.rationale ?? null,
    });
  }
  for (const pos of equityPositions) {
    const dispatch = dispatchByBetLink.get(pos.id);
    out.push({
      betId: pos.id,
      betKind: "equity",
      mode: pos.mode,
      stake: `${pos.qty.toString()} @ ${pos.entryPrice.toString()}`,
      status: pos.status,
      memoId: pos.sourceMemoId,
      memoTitle: memoTitleById.get(pos.sourceMemoId) ?? null,
      agentId: dispatch?.agentId ?? null,
      agentName: dispatch ? agentNameById.get(dispatch.agentId) ?? null : null,
      outcomeAction: dispatch?.outcomeAction ?? null,
      acknowledgedBy: dispatch?.acknowledgedBy ?? null,
      rationale: dispatch?.rationale ?? null,
    });
  }
  return out;
}

type BetSpecRow = {
  id: string;
  kind: string;
  status: string;
  proposition: string;
  horizonAt: Date;
  createdByMemoId: string | null;
  outcome: string | null;
  resolvedAt: Date | null;
  payloadJson: string;
};

function parsePayload(raw: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(raw || "{}");
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function pickBlock(
  payload: Record<string, unknown>,
  key: string,
): Record<string, unknown> {
  const block = payload[key];
  return block && typeof block === "object"
    ? (block as Record<string, unknown>)
    : {};
}

async function loadBetSpecRows(
  organizationId: string,
): Promise<{
  advisory: AdvisoryBetRow[];
  scientific: ScientificBetRow[];
  strategic: StrategicBetRow[];
}> {
  const betSpecApi = (db as unknown as {
    betSpec?: {
      findMany: (args: unknown) => Promise<BetSpecRow[]>;
    };
  }).betSpec;
  if (!betSpecApi) {
    return { advisory: [], scientific: [], strategic: [] };
  }
  const rows = await betSpecApi
    .findMany({
      where: {
        organizationId,
        kind: { in: ["ADVISORY_BET", "SCIENTIFIC_BET", "STRATEGIC_BET"] },
      },
      orderBy: { createdAt: "desc" },
      take: 200,
      select: {
        id: true,
        kind: true,
        status: true,
        proposition: true,
        horizonAt: true,
        createdByMemoId: true,
        outcome: true,
        resolvedAt: true,
        payloadJson: true,
      },
    })
    .catch(() => [] as BetSpecRow[]);
  const advisory: AdvisoryBetRow[] = [];
  const scientific: ScientificBetRow[] = [];
  const strategic: StrategicBetRow[] = [];
  for (const row of rows) {
    const payload = parsePayload(row.payloadJson);
    if (row.kind === "ADVISORY_BET") {
      const block = pickBlock(payload, "advisory_bet");
      advisory.push({
        id: row.id,
        proposition: row.proposition,
        positionPill: (block.position_pill as AdvisoryBetRow["positionPill"]) ?? "NEUTRAL",
        audience: (block.audience as AdvisoryBetRow["audience"]) ?? "PUBLIC",
        publishedAt:
          typeof block.published_at === "string" ? (block.published_at as string) : null,
        publicUrl:
          typeof block.public_url === "string" ? (block.public_url as string) : null,
        memoId: row.createdByMemoId,
        status: row.status,
        outcome: row.outcome,
        reach: typeof block.reach === "number" ? (block.reach as number) : null,
        accuracyScore: null,
      });
    } else if (row.kind === "SCIENTIFIC_BET") {
      const block = pickBlock(payload, "scientific_bet");
      scientific.push({
        id: row.id,
        proposition: row.proposition,
        dataSource: (block.data_source as ScientificBetRow["dataSource"]) ?? "FRED",
        expectedValue: Number(block.expected_value ?? 0),
        tolerance: Number(block.tolerance ?? 0),
        horizonAt: row.horizonAt.toISOString(),
        status: row.status,
        outcome: row.outcome,
        resolvedAt: row.resolvedAt ? row.resolvedAt.toISOString() : null,
        memoId: row.createdByMemoId,
      });
    } else if (row.kind === "STRATEGIC_BET") {
      const block = pickBlock(payload, "strategic_bet");
      strategic.push({
        id: row.id,
        proposition: row.proposition,
        resourceKind:
          (block.resource_kind as StrategicBetRow["resourceKind"]) ?? "FOUNDER_TIME",
        costEstimate: Number(block.cost_estimate ?? 0),
        costUnit: typeof block.cost_unit === "string" ? (block.cost_unit as string) : "hours",
        commitmentReviewAt:
          typeof block.commitment_review_at === "string"
            ? (block.commitment_review_at as string)
            : null,
        status: row.status,
        outcome: row.outcome,
        memoId: row.createdByMemoId,
      });
    }
  }
  return { advisory, scientific, strategic };
}

export default async function UnifiedPortfolioPage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const forecastSurface = await getForecastPortfolioSurface(tenant.organizationId);
  const memoTrace = await loadMemoTrace(tenant.organizationId);
  const betRows = await loadBetSpecRows(tenant.organizationId);

  const liveStatus = {
    forecasts: pillState("FORECASTS_LIVE_TRADING_ENABLED", forecastsAuthorized()),
    equities: pillState("EQUITIES_LIVE_TRADING_ENABLED", equitiesAuthorized()),
  };

  const overview: UnifiedOverview = {
    organizationId: tenant.organizationId,
    netPaperPnlUsd:
      forecastSurface.kpis.realizedPaperPnl + forecastSurface.kpis.unrealizedPaperPnl,
    netPaperPnlCurve: [],
    forecasts: {
      openPositions: forecastSurface.kpis.openPositions,
      realizedPaperPnlUsd: forecastSurface.kpis.realizedPaperPnl,
      unrealizedPaperPnlUsd: forecastSurface.kpis.unrealizedPaperPnl,
    },
    equities: {
      openPositions: 0,
      realizedPaperPnlUsd: 0,
      unrealizedPaperPnlUsd: 0,
    },
    killSwitchEngaged: forecastSurface.mode.failedGates.some(
      (gate) => gate.gateName === "kill_switch_clear",
    ),
    killSwitchReason:
      forecastSurface.mode.failedGates.find(
        (gate) => gate.gateName === "kill_switch_clear",
      )?.reason ?? null,
    liveStatus,
    activePrinciples: collectActivePrinciples(forecastSurface),
  };

  // Binary and directional samples are populated by the API-side surface
  // (Brier-bucketed calibration on the forecasts side, three-class
  // hit-rate on the equities side). The unified page renders the curves
  // honestly: when neither track has resolutions yet, the cards say so.
  const binaryOutcomes: BinaryOutcome[] = [];
  const directionalSamples: DirectionalSample[] = [];

  return (
    <>
      <PortfolioShell
        binaryOutcomes={binaryOutcomes}
        directionalSamples={directionalSamples}
        equitySurface={emptyEquitySurface(tenant.organizationId)}
        overview={overview}
        predictionMarketsContent={
          <ForecastPortfolioView
            addWatchedMarketAction={addWatchedMarket}
            surface={forecastSurface}
          />
        }
        advisoryBets={betRows.advisory}
        scientificBets={betRows.scientific}
        strategicBets={betRows.strategic}
        showStrategicBets={true}
      />
      <MemoTraceSurface rows={memoTrace} />
    </>
  );
}

function MemoTraceSurface({ rows }: { rows: MemoTraceRow[] }) {
  if (rows.length === 0) return null;
  return (
    <section
      className="authed-prose"
      data-testid="memo-trace-surface"
      style={{ marginTop: "2rem" }}
    >
      <h2>Memo trace</h2>
      <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.85rem" }}>
        Open positions that were originated by a memo. Click a memo to see the
        full thesis; the agent column shows who (or what) fired the bet.
      </p>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid var(--rule)" }}>
            <th style={{ padding: "0.4rem 0.4rem 0.4rem 0" }}>Bet</th>
            <th style={{ padding: "0.4rem" }}>Mode</th>
            <th style={{ padding: "0.4rem" }}>Stake</th>
            <th style={{ padding: "0.4rem" }}>Status</th>
            <th style={{ padding: "0.4rem" }}>Memo</th>
            <th style={{ padding: "0.4rem" }}>Agent</th>
            <th style={{ padding: "0.4rem" }}>By</th>
            <th style={{ padding: "0.4rem" }}>Rationale</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.betKind}:${row.betId}`} style={{ borderBottom: "1px solid var(--rule)" }}>
              <td className="mono" style={{ padding: "0.4rem 0.4rem 0.4rem 0" }}>
                {row.betKind}:{row.betId}
              </td>
              <td className="mono" style={{ padding: "0.4rem" }}>{row.mode.toLowerCase()}</td>
              <td className="mono" style={{ padding: "0.4rem" }}>{row.stake}</td>
              <td className="mono" style={{ padding: "0.4rem" }}>{row.status.toLowerCase()}</td>
              <td style={{ padding: "0.4rem" }}>
                <Link href={`/inbox/${row.memoId}`}>{row.memoTitle || row.memoId}</Link>
              </td>
              <td style={{ padding: "0.4rem" }}>
                {row.agentId ? (
                  <Link href={`/portfolio-agents/${row.agentId}`}>
                    {row.agentName || row.agentId}
                  </Link>
                ) : (
                  <span style={{ color: "var(--amber-dim)" }}>(unlinked)</span>
                )}
              </td>
              <td className="mono" style={{ padding: "0.4rem" }}>{row.acknowledgedBy || "—"}</td>
              <td style={{ padding: "0.4rem" }}>{row.rationale || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function collectActivePrinciples(surface: {
  openPositions: { drivingPrinciples: { conclusionId: string; weight: number; snippet: string }[] }[];
}): UnifiedOverview["activePrinciples"] {
  const tally = new Map<
    string,
    { snippet: string; weightSum: number; count: number }
  >();
  for (const position of surface.openPositions) {
    for (const principle of position.drivingPrinciples) {
      const cid = principle.conclusionId;
      const row = tally.get(cid) ?? { snippet: principle.snippet, weightSum: 0, count: 0 };
      row.weightSum += principle.weight;
      row.count += 1;
      if (!row.snippet && principle.snippet) row.snippet = principle.snippet;
      tally.set(cid, row);
    }
  }
  return Array.from(tally.entries())
    .sort(
      ([, a], [, b]) => b.count - a.count || b.weightSum - a.weightSum,
    )
    .slice(0, 5)
    .map(([conclusionId, row]) => ({
      conclusionId,
      snippet: row.snippet,
      weight: row.weightSum / Math.max(row.count, 1),
      positionCount: row.count,
    }));
}
