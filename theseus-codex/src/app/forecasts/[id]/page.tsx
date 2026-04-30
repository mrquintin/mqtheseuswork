import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import {
  getForecast,
  getForecastBets,
  getForecastResolution,
  getForecastSources,
  getMarket,
  getPortfolioCalibration,
} from "@/lib/forecastsApi";
import type {
  CalibrationBucket,
  PublicBet,
  PublicForecast,
  PublicForecastSource,
  PublicMarket,
  PublicResolution,
} from "@/lib/forecastsTypes";
import { SITE } from "@/lib/site";

import AuditTrail from "./AuditTrail";
import BetsPanel from "./BetsPanel";
import ChatPanel from "./ChatPanel";
import { CopyPermalink } from "./CopyPermalink";
import ResolutionPanel from "./ResolutionPanel";
import { ForecastEvidencePanel } from "./SourceDrawer";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ id: string }>;
};

const DAY_MS = 24 * 60 * 60 * 1000;

const heroStyle: CSSProperties = {
  background: "rgba(232, 225, 211, 0.035)",
  border: "1px solid var(--forecasts-border)",
  borderRadius: "6px",
  marginBottom: "1rem",
  padding: "1.15rem",
};

function isForecast404(error: unknown): boolean {
  return error instanceof Error && /^Forecasts API 404\b/.test(error.message);
}

async function resolutionOrNull(id: string): Promise<PublicResolution | null> {
  try {
    return await getForecastResolution(id);
  } catch (error) {
    if (isForecast404(error)) return null;
    throw error;
  }
}

async function calibrationOrNull(): Promise<CalibrationBucket[] | null> {
  try {
    const response = await getPortfolioCalibration();
    return response.items;
  } catch (error) {
    console.error("forecast_calibration_fetch_failed", error);
    return null;
  }
}

function probability(value: number | null): number | null {
  if (value === null || !Number.isFinite(value)) return null;
  return Math.min(1, Math.max(0, value));
}

function probabilityLabel(value: number | null): string {
  const p = probability(value);
  return p === null ? "Abstained" : `${Math.round(p * 100)}% YES`;
}

function priceLabel(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return value.toFixed(2);
}

function edge(prediction: PublicForecast, market: PublicMarket | null): number | null {
  const p = probability(prediction.probability_yes);
  const marketPrice = market?.current_yes_price;
  if (
    p === null ||
    marketPrice === null ||
    marketPrice === undefined ||
    !Number.isFinite(marketPrice)
  ) {
    return null;
  }
  return p - marketPrice;
}

function edgeLabel(value: number | null): string {
  if (value === null) return "edge unavailable";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)} vs market`;
}

function timeToResolution(market: PublicMarket | null, resolution: PublicResolution | null): string {
  if (resolution) return `resolved ${dateLabel(resolution.resolved_at)}`;
  const closeTime = market?.close_time;
  if (!closeTime) return "resolution date open";

  const closesAt = new Date(closeTime).getTime();
  if (!Number.isFinite(closesAt)) return "resolution date open";
  const diff = closesAt - Date.now();
  if (diff <= 0) return "resolution window closed";

  const days = Math.ceil(diff / DAY_MS);
  if (days <= 1) return "resolves within 24h";
  return `resolves in ${days}d`;
}

function dateLabel(iso: string): string {
  const date = new Date(iso);
  if (!Number.isFinite(date.getTime())) return iso;
  return new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function sourceLabel(source: string | null | undefined): string {
  const normalized = source?.trim().toUpperCase();
  if (normalized === "POLYMARKET") return "Polymarket";
  if (normalized === "KALSHI") return "Kalshi";
  return normalized ? normalized.toLowerCase() : "Market";
}

function marketFor(prediction: PublicForecast, fetchedMarket: PublicMarket | null): PublicMarket | null {
  return fetchedMarket ?? prediction.market;
}

function pageDescription(prediction: PublicForecast): string {
  return prediction.reasoning.slice(0, 220).replace(/\s+/g, " ").trim();
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  try {
    const { id } = await params;
    const prediction = await getForecast(id);
    return {
      title: prediction.headline,
      description: pageDescription(prediction),
      openGraph: {
        title: prediction.headline,
        description: pageDescription(prediction),
        images: [
          {
            alt: prediction.headline,
            height: 630,
            url: `${SITE}/api/og/forecasts/${encodeURIComponent(prediction.id)}`,
            width: 1200,
          },
        ],
        siteName: "Theseus Codex",
        type: "article",
        url: `${SITE}/forecasts/${encodeURIComponent(prediction.id)}`,
      },
      twitter: {
        card: "summary_large_image",
        title: prediction.headline,
        description: pageDescription(prediction),
        images: [`${SITE}/api/og/forecasts/${encodeURIComponent(prediction.id)}`],
      },
    };
  } catch {
    return { title: "Forecast" };
  }
}

function Hero({
  market,
  prediction,
  resolution,
}: {
  market: PublicMarket | null;
  prediction: PublicForecast;
  resolution: PublicResolution | null;
}) {
  const p = probability(prediction.probability_yes);
  const modelEdge = edge(prediction, market);
  const modelEdgeColor =
    modelEdge === null
      ? "var(--forecasts-muted)"
      : modelEdge >= 0
        ? "var(--forecasts-prob-yes)"
        : "var(--forecasts-prob-no)";

  return (
    <section aria-label="Forecast summary" style={heroStyle}>
      <div
        style={{
          alignItems: "center",
          color: "var(--forecasts-muted)",
          display: "flex",
          flexWrap: "wrap",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "0.72rem",
          gap: "0.6rem",
          justifyContent: "space-between",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        }}
      >
        <span>
          {sourceLabel(market?.source)} · {market?.category || prediction.topic_hint || "uncategorized"}
        </span>
        <span
          style={{
            alignItems: "center",
            display: "inline-flex",
            flexWrap: "wrap",
            gap: "0.55rem",
            justifyContent: "flex-end",
          }}
        >
          <span>{timeToResolution(market, resolution)}</span>
          <CopyPermalink forecastId={prediction.id} />
        </span>
      </div>

      <h1
        style={{
          color: "var(--forecasts-parchment)",
          fontFamily: "'EB Garamond', serif",
          fontSize: "clamp(2rem, 4vw, 3.2rem)",
          lineHeight: 1.05,
          margin: "0.7rem 0 1rem",
        }}
      >
        {prediction.headline}
      </h1>

      <div>
        <div
          className="mono"
          style={{
            color: "var(--forecasts-cool-gold)",
            fontSize: "0.82rem",
            letterSpacing: "0.08em",
            marginBottom: "0.3rem",
            textAlign: "right",
            textTransform: "uppercase",
          }}
        >
          {probabilityLabel(prediction.probability_yes)}
        </div>
        <div aria-label={`Model probability ${probabilityLabel(prediction.probability_yes)}`} className="forecasts-prob-bar">
          <div className="fill" style={{ width: p === null ? "0%" : `${p * 100}%` }} />
        </div>
      </div>

      <div
        className="mono"
        style={{
          color: "var(--forecasts-parchment-dim)",
          display: "flex",
          flexWrap: "wrap",
          fontSize: "0.82rem",
          gap: "0.9rem",
          justifyContent: "space-between",
          marginTop: "0.8rem",
        }}
      >
        <span>Market YES: {priceLabel(market?.current_yes_price)}</span>
        <span style={{ color: modelEdgeColor, fontWeight: 700 }}>
          {edgeLabel(modelEdge)}
        </span>
      </div>
    </section>
  );
}

export default async function ForecastDetailPage({ params }: PageProps) {
  const { id } = await params;

  let prediction: PublicForecast;
  try {
    prediction = await getForecast(id);
  } catch (error) {
    if (isForecast404(error)) notFound();
    throw error;
  }

  const [marketResult, sources, resolution, paperBets, calibration] = await Promise.all([
    getMarket(prediction.market_id).catch((error) => {
      console.error("forecast_market_fetch_failed", error);
      return null;
    }),
    getForecastSources(id),
    resolutionOrNull(id),
    getForecastBets(id),
    calibrationOrNull(),
  ]);

  const market = marketFor(prediction, marketResult);
  const materializedResolution = resolution ?? prediction.resolution;
  const sourceRows: PublicForecastSource[] = sources;
  const bets: PublicBet[] = paperBets;

  return (
    <>
      <div className="forecast-detail-grid">
        <aside className="forecast-detail-audit">
          <AuditTrail citations={prediction.citations} sources={sourceRows} />
        </aside>

        <main className="forecast-detail-main">
          <Hero
            market={market}
            prediction={prediction}
            resolution={materializedResolution}
          />

          <ForecastEvidencePanel prediction={prediction} sources={sourceRows} />

          <ResolutionPanel
            calibration={calibration}
            market={market}
            resolution={materializedResolution}
          />

          <BetsPanel paperBets={bets} />

          <ChatPanel predictionId={prediction.id} sources={sourceRows} />
        </main>
      </div>

      <style>{`
        .forecast-detail-grid {
          align-items: start;
          display: grid;
          gap: 1rem;
          grid-template-columns: minmax(180px, 250px) minmax(0, 1fr);
        }

        .forecast-detail-main {
          min-width: 0;
        }

        .forecast-evidence-drawer {
          margin-top: 1rem;
        }

        @media (min-width: 1080px) {
          .forecast-detail-main > section[aria-label="Forecast reasoning and citations"] {
            display: grid;
            gap: 1rem;
            grid-template-columns: minmax(0, 1fr) minmax(260px, 320px);
          }

          .forecast-detail-main > section[aria-label="Forecast reasoning and citations"] > div:first-child,
          .forecast-detail-main > section[aria-label="Forecast reasoning and citations"] > nav {
            grid-column: 1;
          }

          .forecast-evidence-drawer {
            grid-column: 2;
            grid-row: 1 / span 2;
            margin-top: 0;
          }
        }

        @media (max-width: 900px) {
          .forecast-detail-grid {
            grid-template-columns: minmax(0, 1fr);
          }

          .forecast-detail-audit {
            order: 2;
          }

          .forecast-detail-main {
            order: 1;
          }
        }
      `}</style>
    </>
  );
}
