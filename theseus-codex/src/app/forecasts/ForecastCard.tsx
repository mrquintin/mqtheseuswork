import type { CSSProperties } from "react";
import Link from "next/link";

import type { PublicForecast } from "@/lib/forecastsTypes";
import { relativeTime } from "@/lib/relativeTime";

export type ForecastCardStatus =
  | "PUBLISHED"
  | "RESOLVED-CORRECT"
  | "RESOLVED-INCORRECT"
  | "RESOLVED-CANCELLED";

const DAY_MS = 24 * 60 * 60 * 1000;
const EDGE_DISPLAY_THRESHOLD = 0.05;

const cardStyle: CSSProperties = {
  background: "var(--forecasts-bg-elevated)",
  border: "1px solid var(--forecasts-border)",
  borderRadius: "6px",
  boxShadow: "0 12px 32px rgba(0, 0, 0, 0.18)",
  color: "var(--forecasts-parchment)",
  display: "block",
  padding: "1rem 1rem 0.9rem",
  textDecoration: "none",
};

const metaRowStyle: CSSProperties = {
  alignItems: "center",
  color: "var(--forecasts-muted)",
  display: "flex",
  flexWrap: "wrap",
  fontSize: "0.72rem",
  gap: "0.45rem",
  letterSpacing: "0.05em",
  marginTop: "0.85rem",
  textTransform: "uppercase",
};

const pillBaseStyle: CSSProperties = {
  borderRadius: "999px",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.62rem",
  fontWeight: 700,
  letterSpacing: "0.08em",
  lineHeight: 1,
  padding: "0.34rem 0.48rem",
  textTransform: "uppercase",
};

const headlineStyle: CSSProperties = {
  color: "var(--forecasts-parchment)",
  fontFamily: "'EB Garamond', serif",
  fontSize: "1.17rem",
  lineHeight: 1.24,
  margin: "0.72rem 0 0.9rem",
};

const marketRowStyle: CSSProperties = {
  alignItems: "center",
  color: "var(--forecasts-parchment-dim)",
  display: "flex",
  flexWrap: "wrap",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.76rem",
  gap: "0.55rem",
  justifyContent: "space-between",
  marginTop: "0.55rem",
};

function clampProbability(value: number | null): number | null {
  if (value === null || !Number.isFinite(value)) return null;
  return Math.min(1, Math.max(0, value));
}

function formatProbability(value: number | null): string {
  const probability = clampProbability(value);
  if (probability === null) return "ABSTAINED";
  return `${Math.round(probability * 100)}% YES`;
}

function formatMarketPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return value.toFixed(2);
}

function sourceLabel(source: string | undefined): string {
  const normalized = source?.trim().toUpperCase();
  if (normalized === "POLYMARKET") return "Polymarket";
  if (normalized === "KALSHI") return "Kalshi";
  return normalized ? normalized.toLowerCase() : "Market";
}

function resolutionTiming(forecast: PublicForecast): string {
  if (forecast.resolution) return `resolved ${relativeTime(forecast.resolution.resolved_at)}`;

  const closeTime = forecast.market?.close_time;
  if (!closeTime) return "resolution date open";

  const closesAt = new Date(closeTime).getTime();
  if (!Number.isFinite(closesAt)) return "resolution date open";

  const diff = closesAt - Date.now();
  if (diff < 0) return "resolution window closed";

  const days = Math.ceil(diff / DAY_MS);
  if (days <= 0) return "resolves today";
  return `resolves in ${days}d`;
}

function modelWasCorrect(forecast: PublicForecast): boolean {
  const outcome = forecast.resolution?.market_outcome?.trim().toUpperCase();
  const probability = clampProbability(forecast.probability_yes);
  if (!outcome || probability === null) return false;
  if (outcome === "YES") return probability >= 0.5;
  if (outcome === "NO") return probability < 0.5;
  return false;
}

export function forecastCardStatus(forecast: PublicForecast): ForecastCardStatus {
  const existingStatus = forecast.status.trim().toUpperCase();
  if (
    existingStatus === "RESOLVED-CORRECT" ||
    existingStatus === "RESOLVED-INCORRECT" ||
    existingStatus === "RESOLVED-CANCELLED"
  ) {
    return existingStatus;
  }

  const outcome = forecast.resolution?.market_outcome?.trim().toUpperCase();
  if (outcome === "CANCELLED" || outcome === "AMBIGUOUS") return "RESOLVED-CANCELLED";
  if (forecast.resolution || existingStatus === "RESOLVED") {
    return modelWasCorrect(forecast) ? "RESOLVED-CORRECT" : "RESOLVED-INCORRECT";
  }
  return "PUBLISHED";
}

function statusStyle(status: ForecastCardStatus): CSSProperties {
  const color =
    status === "RESOLVED-CORRECT"
      ? "var(--forecasts-prob-yes)"
      : status === "RESOLVED-INCORRECT"
        ? "var(--forecasts-prob-no)"
        : status === "RESOLVED-CANCELLED"
          ? "var(--forecasts-muted)"
          : "var(--forecasts-cool-gold)";

  return {
    ...pillBaseStyle,
    background: `color-mix(in srgb, ${color} 14%, transparent)`,
    border: `1px solid ${color}`,
    color,
  };
}

function edgeFor(forecast: PublicForecast): number | null {
  const probability = clampProbability(forecast.probability_yes);
  const marketPrice = forecast.market?.current_yes_price;
  if (
    probability === null ||
    marketPrice === null ||
    marketPrice === undefined ||
    !Number.isFinite(marketPrice)
  ) {
    return null;
  }
  const edge = probability - marketPrice;
  return Math.abs(edge) < EDGE_DISPLAY_THRESHOLD ? null : edge;
}

function edgeColor(edge: number): string {
  return edge > 0 ? "var(--forecasts-prob-yes)" : "var(--forecasts-prob-no)";
}

interface ForecastCardProps {
  forecast: PublicForecast;
  className?: string;
}

export default function ForecastCard({ forecast, className }: ForecastCardProps) {
  const href = `/forecasts/${encodeURIComponent(forecast.id)}`;
  const probability = clampProbability(forecast.probability_yes);
  const probabilityLabel = formatProbability(forecast.probability_yes);
  const status = forecastCardStatus(forecast);
  const edge = edgeFor(forecast);
  const marketSource = sourceLabel(forecast.market?.source);
  const category = forecast.market?.category || forecast.topic_hint || "uncategorized";
  const sourceCount = forecast.citations.length;

  return (
    <Link
      aria-label={`Forecast: ${forecast.headline}`}
      className={className}
      href={href}
      style={cardStyle}
    >
      <article>
        <div
          style={{
            alignItems: "center",
            display: "flex",
            gap: "0.65rem",
            justifyContent: "space-between",
          }}
        >
          <span style={statusStyle(status)}>{status}</span>
          <span
            className="mono"
            style={{
              color: "var(--forecasts-muted)",
              fontSize: "0.66rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
            }}
          >
            ▦ {sourceCount} {sourceCount === 1 ? "source" : "sources"}
          </span>
        </div>

        <h2 style={headlineStyle}>{forecast.headline}</h2>

        <div style={{ position: "relative" }}>
          <span
            className="mono"
            style={{
              color: "var(--forecasts-cool-gold)",
              display: "block",
              fontSize: "0.75rem",
              letterSpacing: "0.08em",
              marginBottom: "0.28rem",
              textAlign: "right",
            }}
          >
            {probabilityLabel}
          </span>
          <div
            aria-label={`Model probability ${probabilityLabel}`}
            className="forecasts-prob-bar"
          >
            <div
              className="fill"
              style={{
                width: probability === null ? "0%" : `${probability * 100}%`,
              }}
            />
          </div>
        </div>

        <div style={marketRowStyle}>
          <span>Market: {formatMarketPrice(forecast.market?.current_yes_price)}</span>
          {edge !== null ? (
            <span
              aria-label={`model edge ${edge >= 0 ? "+" : ""}${edge.toFixed(2)}`}
              style={{ color: edgeColor(edge), fontWeight: 700 }}
            >
              {edge > 0 ? "▲" : "▼"} {edge >= 0 ? "+" : ""}
              {edge.toFixed(2)}
            </span>
          ) : null}
        </div>

        <div style={metaRowStyle}>
          <span
            style={{
              ...pillBaseStyle,
              border: "1px solid var(--forecasts-border)",
              color: "var(--forecasts-parchment-dim)",
            }}
          >
            {marketSource}
          </span>
          <span>{category}</span>
          <span>· {resolutionTiming(forecast)}</span>
        </div>
      </article>
    </Link>
  );
}
