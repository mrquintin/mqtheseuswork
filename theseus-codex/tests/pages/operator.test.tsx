import { renderToStaticMarkup } from "react-dom/server";
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LiveBetLedger, { applyOperatorStreamFrame } from "@/app/(authed)/forecasts/operator/LiveBetLedger";
import { parseOperatorStreamFrame } from "@/app/(authed)/forecasts/operator/OperatorBetStream";
import PendingConfirmations, {
  CONFIRM_GATE_MESSAGES,
  type ConfirmGateCode,
  type ConfirmGateContext,
} from "@/app/(authed)/forecasts/operator/PendingConfirmations";
import {
  postKillSwitchDisengage,
  postKillSwitchEngage,
} from "@/app/(authed)/forecasts/operator/KillSwitchPanel";
import { middleware } from "@/middleware";
import type { OperatorBet, PublicForecast, PublicMarket } from "@/lib/forecastsTypes";

const NOW = "2026-04-30T12:00:00.000Z";

function market(overrides: Partial<PublicMarket> = {}): PublicMarket {
  return {
    id: "market-operator",
    organization_id: "org-operator",
    source: "POLYMARKET",
    external_id: "poly-operator",
    title: "Operator market",
    description: null,
    resolution_criteria: null,
    category: "policy",
    current_yes_price: 0.52,
    current_no_price: 0.48,
    volume: 1000,
    open_time: NOW,
    close_time: null,
    resolved_at: null,
    resolved_outcome: null,
    raw_payload: {},
    status: "OPEN",
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

function prediction(overrides: Partial<PublicForecast> = {}): PublicForecast {
  return {
    id: "prediction-operator",
    market_id: "market-operator",
    organization_id: "org-operator",
    probability_yes: 0.64,
    confidence_low: 0.54,
    confidence_high: 0.74,
    headline: "Operator fixture prediction",
    reasoning: "Fixture reasoning.",
    status: "PUBLISHED",
    abstention_reason: null,
    topic_hint: "policy",
    model_name: "fixture",
    live_authorized_at: NOW,
    created_at: NOW,
    updated_at: NOW,
    revoked_sources_count: 0,
    market: market(),
    citations: [],
    resolution: null,
    ...overrides,
  };
}

function bet(overrides: Partial<OperatorBet> = {}): OperatorBet {
  return {
    id: "bet-operator",
    prediction_id: "prediction-operator",
    organization_id: "org-operator",
    mode: "LIVE",
    exchange: "POLYMARKET",
    side: "YES",
    stake_usd: 100,
    entry_price: 0.52,
    exit_price: null,
    status: "AUTHORIZED",
    external_order_id: "order-old",
    client_order_id: "client-operator",
    settlement_pnl_usd: null,
    live_authorized_at: NOW,
    confirmed_at: null,
    submitted_at: null,
    created_at: NOW,
    settled_at: null,
    ...overrides,
  };
}

function context(overrides: Partial<ConfirmGateContext> = {}): ConfirmGateContext {
  return {
    configuredExchanges: ["POLYMARKET"],
    dailyLossUsd: 0,
    killSwitchEngaged: false,
    liveBalanceUsd: 1000,
    liveTradingEnabled: true,
    maxDailyLossUsd: 500,
    maxStakeUsd: 250,
    ...overrides,
  };
}

describe("operator page confirmation flow", () => {
  const visibleGateCases: Array<[ConfirmGateCode, Partial<ConfirmGateContext>, Partial<OperatorBet>]> = [
    ["DISABLED", { liveTradingEnabled: false }, {}],
    ["NOT_CONFIGURED", { configuredExchanges: [] }, {}],
    ["STAKE_OVER_CEILING", { maxStakeUsd: 25 }, {}],
    ["DAILY_LOSS_OVER_CEILING", { dailyLossUsd: 600, maxDailyLossUsd: 500 }, {}],
    ["KILL_SWITCH_ENGAGED", { killSwitchEngaged: true }, {}],
    ["INSUFFICIENT_BALANCE", { liveBalanceUsd: 10 }, {}],
  ];

  for (const [code, contextOverrides, betOverrides] of visibleGateCases) {
    it(`disables CONFIRM with ${code} tooltip`, () => {
      const html = renderToStaticMarkup(
        <PendingConfirmations
          context={context(contextOverrides)}
          predictionsById={{ "prediction-operator": prediction() }}
          rows={[bet(betOverrides)]}
        />,
      );

      expect(html).toContain("disabled");
      expect(html).toContain(`${code}: ${CONFIRM_GATE_MESSAGES[code]}`);
    });
  }

  it("hides CONFIRM when prediction live_authorized_at is null", () => {
    const html = renderToStaticMarkup(
      <PendingConfirmations
        context={context()}
        predictionsById={{ "prediction-operator": prediction({ live_authorized_at: null }) }}
        rows={[bet()]}
      />,
    );

    expect(html).not.toContain("data-confirm-bet-id");
    expect(html).toContain("data-confirm-hidden-reason=\"NOT_AUTHORIZED\"");
  });

  it("renders a real CANCEL control for authorized live bets", () => {
    const html = renderToStaticMarkup(
      <PendingConfirmations
        context={context()}
        predictionsById={{ "prediction-operator": prediction() }}
        rows={[bet()]}
      />,
    );

    expect(html).toContain("data-cancel-bet-id=\"bet-operator\"");
    expect(html).toContain("Cancel this authorized live bet before exchange submission.");
  });
});

describe("operator kill switch client", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init: RequestInit) => {
        const body = JSON.parse(String(init.body || "{}"));
        const engaged = String(url).endsWith("/engage");
        return new Response(
          JSON.stringify({
            kill_switch_engaged: engaged,
            kill_switch_reason: engaged ? body.reason : null,
            organization_id: "org-operator",
            updated_at: NOW,
          }),
          { headers: { "content-type": "application/json" }, status: 200 },
        );
      }),
    );
  });

  it("round-trips engage and disengage through the operator API mock", async () => {
    const engaged = await postKillSwitchEngage("OPERATOR", "Manual operator halt");
    const disengaged = await postKillSwitchDisengage("Reviewed the incident and cleared live risk.");
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;

    expect(engaged.kill_switch_engaged).toBe(true);
    expect(engaged.kill_switch_reason).toBe("OPERATOR");
    expect(disengaged.kill_switch_engaged).toBe(false);
    expect(calls[0][0]).toBe("/api/forecasts/operator/kill-switch/engage");
    expect(calls[1][0]).toBe("/api/forecasts/operator/kill-switch/disengage");
  });
});

describe("operator stream reducer", () => {
  it("updates a ledger row in place when bet.filled arrives", () => {
    const frame = parseOperatorStreamFrame(
      "bet.filled",
      JSON.stringify(
        bet({
          external_order_id: "order-filled",
          settlement_pnl_usd: 42.5,
          status: "FILLED",
        }),
      ),
    );
    expect(frame?.bet?.status).toBe("FILLED");

    const rows = applyOperatorStreamFrame([bet()], frame!);
    expect(rows).toHaveLength(1);
    expect(rows[0].status).toBe("FILLED");
    expect(rows[0].external_order_id).toBe("order-filled");

    const html = renderToStaticMarkup(
      <LiveBetLedger
        initialRows={rows}
        predictionsById={{ "prediction-operator": prediction() }}
      />,
    );
    expect(html).toContain("order-filled");
    expect(html).toContain("FILLED");
  });
});

describe("operator auth gate", () => {
  it("redirects the /forecasts/operator path with no cookie", () => {
    const res = middleware(new NextRequest("http://localhost:3000/forecasts/operator"));

    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/login?next=%2Fforecasts%2Foperator");
  });

  it("redirects /forecasts/operator without a founder session", async () => {
    vi.resetModules();
    vi.doMock("@/lib/auth", () => ({ getFounder: vi.fn(async () => null) }));
    const mod = await import("@/app/(authed)/forecasts/operator/page");

    await expect(mod.default()).rejects.toThrow("NEXT_REDIRECT");

    vi.doUnmock("@/lib/auth");
  });

  it("rejects read-only founders in the operator API proxy", async () => {
    vi.resetModules();
    vi.doMock("@/lib/auth", () => ({
      getFounder: vi.fn(async () => ({
        id: "viewer-founder",
        role: "viewer",
      })),
    }));
    const route = await import("@/app/(authed)/api/forecasts/operator/live-bets/route");

    const res = await route.GET(
      new Request("http://localhost:3000/api/forecasts/operator/live-bets") as never,
    );
    const body = await res.json();

    expect(res.status).toBe(403);
    expect(body.code).toBe("viewer_write_forbidden");

    vi.doUnmock("@/lib/auth");
  });
});
