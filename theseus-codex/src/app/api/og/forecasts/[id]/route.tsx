import { ImageResponse } from "next/og";

import { getForecast, getMarket } from "@/lib/forecastsApi";
import type { PublicForecast, PublicMarket } from "@/lib/forecastsTypes";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const size = {
  height: 630,
  width: 1200,
};

function clampProbability(value: number | null): number | null {
  if (value === null || !Number.isFinite(value)) return null;
  return Math.min(1, Math.max(0, value));
}

function probabilityLabel(value: number | null): string {
  const probability = clampProbability(value);
  return probability === null ? "Abstained" : `${Math.round(probability * 100)}% YES`;
}

function marketPriceLabel(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return value.toFixed(2);
}

function edgeFor(prediction: PublicForecast, market: PublicMarket | null): number | null {
  const probability = clampProbability(prediction.probability_yes);
  const marketPrice = market?.current_yes_price;
  if (
    probability === null ||
    marketPrice === null ||
    marketPrice === undefined ||
    !Number.isFinite(marketPrice)
  ) {
    return null;
  }
  return probability - marketPrice;
}

function edgeLabel(value: number | null): string {
  if (value === null) return "edge unavailable";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)} edge`;
}

function metric(label: string, value: string, color = "#e8e1d3") {
  return (
    <div
      style={{
        border: "2px solid rgba(232, 225, 211, 0.16)",
        borderRadius: 18,
        display: "flex",
        flexDirection: "column",
        padding: "22px 24px",
        width: 300,
      }}
    >
      <div
        style={{
          color: "#847c6c",
          display: "flex",
          fontSize: 24,
          letterSpacing: 4,
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>
      <div
        style={{
          color,
          display: "flex",
          fontSize: 42,
          marginTop: 10,
        }}
      >
        {value}
      </div>
    </div>
  );
}

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const prediction = await getForecast(id);
  const market =
    prediction.market ??
    (await getMarket(prediction.market_id).catch(() => null));
  const edge = edgeFor(prediction, market);
  const edgeColor =
    edge === null ? "#b0a896" : edge >= 0 ? "#6fa15c" : "#b95c5c";

  return new ImageResponse(
    (
      <div
        style={{
          background:
            "linear-gradient(135deg, #14130f 0%, #1c1a14 52%, #2a261d 100%)",
          color: "#e8e1d3",
          display: "flex",
          flexDirection: "column",
          fontFamily: "serif",
          height: "100%",
          justifyContent: "space-between",
          padding: "64px",
          width: "100%",
        }}
      >
        <div
          style={{
            color: "#c4a04b",
            display: "flex",
            fontSize: 28,
            letterSpacing: 6,
            textTransform: "uppercase",
          }}
        >
          Theseus Forecast
        </div>
        <div
          style={{
            color: "#e8e1d3",
            display: "flex",
            fontSize: prediction.headline.length > 90 ? 48 : 58,
            lineHeight: 1.08,
            maxWidth: 1040,
          }}
        >
          {prediction.headline}
        </div>
        <div style={{ display: "flex", gap: 24 }}>
          {metric("Model", probabilityLabel(prediction.probability_yes), "#c4a04b")}
          {metric("Market", marketPriceLabel(market?.current_yes_price))}
          {metric("Edge", edgeLabel(edge), edgeColor)}
        </div>
      </div>
    ),
    size,
  );
}
