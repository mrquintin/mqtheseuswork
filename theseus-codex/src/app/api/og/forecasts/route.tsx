import { ImageResponse } from "next/og";

import { getPortfolioSummary } from "@/lib/forecastsApi";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const size = {
  height: 630,
  width: 1200,
};

function brierLabel(value: number | null | undefined): string | null {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return null;
  }
  return value.toFixed(3);
}

export async function GET() {
  let meanBrier: string | null = null;

  try {
    const summary = await getPortfolioSummary();
    meanBrier = brierLabel(summary.mean_brier_90d);
  } catch {
    meanBrier = null;
  }

  return new ImageResponse(
    (
      <div
        style={{
          alignItems: "stretch",
          background:
            "linear-gradient(135deg, #1c1a14 0%, #2a261d 46%, #14130f 100%)",
          color: "#e8e1d3",
          display: "flex",
          flexDirection: "column",
          fontFamily: "serif",
          height: "100%",
          justifyContent: "space-between",
          padding: "72px",
          width: "100%",
        }}
      >
        <div
          style={{
            color: "#c4a04b",
            display: "flex",
            fontSize: 30,
            letterSpacing: 7,
            textTransform: "uppercase",
          }}
        >
          Theseus Codex
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div
            style={{
              color: "#e8e1d3",
              display: "flex",
              fontSize: 92,
              lineHeight: 1,
            }}
          >
            Forecasts
          </div>
          <div
            style={{
              color: "#b0a896",
              display: "flex",
              fontSize: 34,
              marginTop: 24,
            }}
          >
            Live predictions, source-grounded.
          </div>
        </div>
        <div
          style={{
            borderTop: "2px solid rgba(196, 160, 75, 0.55)",
            color: "#c4a04b",
            display: "flex",
            fontSize: 34,
            paddingTop: 28,
          }}
        >
          {meanBrier ? `Mean Brier 90d: ${meanBrier}` : "Calibration updates as markets resolve"}
        </div>
      </div>
    ),
    size,
  );
}
