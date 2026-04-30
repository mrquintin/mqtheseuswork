import { execFileSync } from "child_process";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import BetLogTable from "@/app/forecasts/portfolio/BetLogTable";
import BrierTimeChart from "@/app/forecasts/portfolio/BrierTimeChart";
import CalibrationChart, {
  bucketForProbability,
  buildCalibrationBucketsFromResolutions,
} from "@/app/forecasts/portfolio/CalibrationChart";
import PortfolioShell from "@/app/forecasts/portfolio/PortfolioShell";
import StatusStrip from "@/app/forecasts/portfolio/StatusStrip";
import type { CalibrationBucket, PortfolioPoint, PortfolioSummary, PublicBet } from "@/lib/forecastsTypes";

const NOW = "2026-04-29T12:00:00.000Z";

function summary(overrides: Partial<PortfolioSummary> & Record<string, unknown> = {}): PortfolioSummary & Record<string, unknown> {
  return {
    organization_id: "org-portfolio",
    paper_balance_usd: 10000,
    paper_pnl_curve: [],
    calibration: [],
    mean_brier_90d: null,
    total_bets: 0,
    kill_switch_engaged: false,
    kill_switch_reason: null,
    updated_at: NOW,
    ...overrides,
  };
}

function bet(overrides: Partial<PublicBet> & Record<string, unknown> = {}): PublicBet & Record<string, unknown> {
  return {
    id: "bet-1",
    prediction_id: "prediction-1",
    mode: "PAPER",
    exchange: "POLYMARKET",
    side: "YES",
    stake_usd: 100,
    entry_price: 0.61,
    exit_price: 0.9,
    status: "SETTLED",
    settlement_pnl_usd: 47.54,
    created_at: NOW,
    settled_at: "2026-04-30T12:00:00.000Z",
    prediction_headline: "Fixture prediction headline",
    ...overrides,
  };
}

function calibrationBucket(overrides: Partial<CalibrationBucket> = {}): CalibrationBucket {
  return {
    bucket: 0.7,
    prediction_count: 10,
    resolved_count: 10,
    mean_probability_yes: 0.74,
    empirical_yes_rate: 0.6,
    mean_brier: 0.21,
    ...overrides,
  };
}

function pnlPoint(overrides: Partial<PortfolioPoint> = {}): PortfolioPoint {
  return {
    ts: NOW,
    paper_balance_usd: 10000,
    paper_pnl_usd: 0,
    ...overrides,
  };
}

function deterministicCalibrationRows() {
  return Array.from({ length: 30 }, (_, index) => {
    const bucket = index < 10 ? 0.7 : index < 20 ? 0.2 : 0.5;
    const probability_yes = bucket + 0.03;
    const market_outcome =
      index >= 25 ? "CANCELLED" : index < 6 || (index >= 10 && index < 12) ? "YES" : "NO";
    const actual = market_outcome === "YES" ? 1 : 0;
    return {
      probability_yes,
      market_outcome,
      brier_score: market_outcome === "CANCELLED" ? null : (probability_yes - actual) ** 2,
    };
  });
}

function pythonResolutionTrackerAggregate(rows: Array<{ probability_yes: number; market_outcome: string | null }>) {
  const script = String.raw`
import contextlib
import io
import json
import sys

with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    from noosphere.forecasts.resolution_tracker import calibration_bucket

rows = json.load(sys.stdin)
groups = {}
for row in rows:
    outcome = (row.get("market_outcome") or "").upper()
    if outcome not in {"YES", "NO"}:
        continue
    bucket = float(calibration_bucket(row["probability_yes"]))
    key = f"{bucket:.1f}"
    if key not in groups:
        groups[key] = {"bucket": bucket, "resolved_count": 0, "yes_count": 0}
    groups[key]["resolved_count"] += 1
    if outcome == "YES":
        groups[key]["yes_count"] += 1

out = []
for key in sorted(groups, key=lambda value: float(value)):
    group = groups[key]
    out.append({
        "bucket": group["bucket"],
        "resolved_count": group["resolved_count"],
        "empirical_yes_rate": group["yes_count"] / group["resolved_count"],
    })
print(json.dumps(out, sort_keys=True))
`;
  const noospherePath = path.resolve(process.cwd(), "../noosphere");
  const stdout = execFileSync("python3", ["-c", script], {
    cwd: process.cwd(),
    env: { ...process.env, PYTHONPATH: noospherePath },
    input: JSON.stringify(rows),
  }).toString("utf8");
  return JSON.parse(stdout) as Array<{
    bucket: number;
    empirical_yes_rate: number;
    resolved_count: number;
  }>;
}

describe("forecasts portfolio page", () => {
  it("computes empirical calibration rate per bucket and excludes cancelled resolutions", () => {
    const buckets = buildCalibrationBucketsFromResolutions(deterministicCalibrationRows());
    const bucket07 = buckets.find((bucket) => bucket.bucket === 0.7);
    const bucket05 = buckets.find((bucket) => bucket.bucket === 0.5);

    expect(bucket07?.resolved_count).toBe(10);
    expect(bucket07?.empirical_yes_rate).toBe(0.6);
    expect(bucket05?.resolved_count).toBe(5);
    expect(bucket05?.empirical_yes_rate).toBe(0);

    const html = renderToStaticMarkup(<CalibrationChart buckets={buckets} />);
    expect(html).toContain("60% YES (n=10)");
  });

  it("round-trips calibration buckets against the Python resolution tracker", () => {
    const rows = Array.from({ length: 80 }, (_, index) => {
      const probability_yes = (((index * 37) % 100) + 0.5) / 100;
      const market_outcome = index % 11 === 0 ? "CANCELLED" : index % 3 === 0 ? "YES" : "NO";
      return { probability_yes, market_outcome };
    });
    const python = pythonResolutionTrackerAggregate(rows);
    const ts = buildCalibrationBucketsFromResolutions(rows).map((bucket) => ({
      bucket: bucket.bucket,
      empirical_yes_rate: bucket.empirical_yes_rate,
      resolved_count: bucket.resolved_count,
    }));

    expect(bucketForProbability(1)).toBe(0.9);
    expect(ts).toEqual(python);
  });

  it("StatusStrip shows ENGAGED with the red palette when the kill switch is active", () => {
    const html = renderToStaticMarkup(
      <StatusStrip
        killSwitchEngaged
        killSwitchReason="daily loss ceiling"
        liveTradingEnabled={false}
        updatedAt={NOW}
      />,
    );

    expect(html).toContain("ENGAGED");
    expect(html).toContain('data-kill-switch-palette="red"');
    expect(html).toContain("daily loss ceiling");
  });

  it("BetLogTable hides LIVE mode bets from the public table", () => {
    const html = renderToStaticMarkup(
      <BetLogTable
        bets={[
          bet({ id: "paper-bet", prediction_headline: "Visible paper prediction" }),
          bet({
            id: "live-bet",
            mode: "LIVE",
            prediction_headline: "Hidden live prediction",
            settlement_pnl_usd: null,
          }),
        ]}
      />,
    );

    expect(html).toContain("Visible paper prediction");
    expect(html).not.toContain("Hidden live prediction");
    expect(html).not.toContain("live-bet");
  });

  it("BrierTimeChart renders an empty state for zero resolved observations", () => {
    const html = renderToStaticMarkup(<BrierTimeChart points={[]} />);

    expect(html).toContain("No resolved Brier observations yet");
  });

  it("hides the live tab when liveTradingEnabled is false and shows it when true", () => {
    const baseProps = {
      bets: [bet()],
      brierPoints: [],
      calibration: [calibrationBucket()],
      summary: summary({
        paper_pnl_curve: [pnlPoint()],
      }),
    };
    const hidden = renderToStaticMarkup(<PortfolioShell {...baseProps} />);
    const visible = renderToStaticMarkup(
      <PortfolioShell
        {...baseProps}
        summary={summary({
          liveTradingEnabled: true,
          paper_pnl_curve: [pnlPoint()],
        })}
      />,
    );

    expect(hidden).not.toContain("Live bets");
    expect(visible).toContain("Live bets");
    expect(visible).toContain("/forecasts/operator");
  });
});
