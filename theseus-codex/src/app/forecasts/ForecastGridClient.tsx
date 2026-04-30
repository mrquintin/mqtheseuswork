"use client";

import { useMemo, useRef } from "react";

import type { PublicForecast } from "@/lib/forecastsTypes";
import { useLiveForecasts } from "@/lib/useLiveForecasts";

import ForecastCard from "./ForecastCard";
import LivePulse from "./LivePulse";

interface ForecastGridClientProps {
  seed: PublicForecast[];
}

function EmptyForecastsMessage() {
  return (
    <div
      style={{
        background: "rgba(232, 225, 211, 0.035)",
        border: "1px solid var(--forecasts-border)",
        borderLeft: "4px solid var(--forecasts-cool-gold)",
        borderRadius: "6px",
        color: "var(--forecasts-parchment-dim)",
        padding: "1rem",
      }}
    >
      No predictions yet — the model abstains until it has at least 3 verifiable
      sources.
    </div>
  );
}

export default function ForecastGridClient({ seed }: ForecastGridClientProps) {
  const seedIds = useRef(new Set(seed.map((forecast) => forecast.id)));
  const { forecasts, resolutions, connected } = useLiveForecasts(seed);
  const materializedForecasts = useMemo(
    () =>
      forecasts.map((forecast) => {
        const resolution = resolutions[forecast.id];
        return resolution && forecast.resolution?.id !== resolution.id
          ? { ...forecast, status: "RESOLVED", resolution }
          : forecast;
      }),
    [forecasts, resolutions],
  );

  return (
    <section aria-label="Forecast predictions">
      <div
        aria-live="polite"
        style={{
          alignItems: "center",
          border: "1px solid var(--forecasts-border)",
          borderRadius: "999px",
          color: "var(--forecasts-parchment-dim)",
          display: "inline-flex",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "0.74rem",
          gap: "0.45rem",
          letterSpacing: "0.08em",
          marginBottom: "1rem",
          padding: "0.4rem 0.7rem",
          textTransform: "uppercase",
        }}
      >
        <LivePulse active={connected} label={connected ? "live" : "Reconnecting…"} />
      </div>

      {materializedForecasts.length ? (
        <div aria-live="polite" className="forecasts-grid">
          {materializedForecasts.map((forecast) => (
            <ForecastCard
              key={forecast.id}
              className={seedIds.current.has(forecast.id) ? undefined : "currents-fade-in"}
              forecast={forecast}
            />
          ))}
        </div>
      ) : (
        <EmptyForecastsMessage />
      )}

      <style jsx>{`
        .forecasts-grid {
          display: grid;
          gap: 0.9rem;
          grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
        }

        @media (max-width: 720px) {
          .forecasts-grid {
            grid-template-columns: minmax(0, 1fr);
          }
        }
      `}</style>
    </section>
  );
}
