"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useMemo, useRef, useState } from "react";

import OpinionCard from "@/app/currents/OpinionCard";
import ForecastCard from "@/app/forecasts/ForecastCard";
import LivePulse from "@/app/forecasts/LivePulse";
import type { PublicOpinion } from "@/lib/currentsTypes";
import type { PublicForecast } from "@/lib/forecastsTypes";
import { useLiveForecasts } from "@/lib/useLiveForecasts";
import { useLiveOpinions } from "@/lib/useLiveOpinions";

type ActiveTab = "currents" | "forecasts";

interface DualPulseClientProps {
  initialForecasts: PublicForecast[];
  initialOpinions: PublicOpinion[];
}

const WINDOW_SIZE = 4;

function EmptyPane({ children }: { children: ReactNode }) {
  return (
    <div
      className="dual-pulse-empty"
      role="status"
      style={{
        background: "rgba(232, 225, 211, 0.05)",
        border: "1px solid rgba(232, 225, 211, 0.16)",
        borderRadius: "6px",
        color: "var(--currents-parchment-dim)",
        fontStyle: "italic",
        lineHeight: 1.55,
        padding: "1rem",
      }}
    >
      {children}
    </div>
  );
}

function PaneHeader({
  connected,
  label,
  title,
  tone,
}: {
  connected: boolean;
  label: string;
  title: string;
  tone: "currents" | "forecasts";
}) {
  return (
    <div
      style={{
        alignItems: "center",
        display: "flex",
        gap: "0.65rem",
        justifyContent: "space-between",
        marginBottom: "0.85rem",
      }}
    >
      <h3
        className="mono"
        style={{
          color:
            tone === "currents"
              ? "var(--currents-amber)"
              : "var(--forecasts-cool-gold)",
          fontSize: "0.68rem",
          letterSpacing: "0.2em",
          margin: 0,
          textTransform: "uppercase",
        }}
      >
        {title}
      </h3>
      <div
        aria-live="polite"
        className="mono"
        style={{
          alignItems: "center",
          color:
            tone === "currents"
              ? "var(--currents-parchment-dim)"
              : "var(--forecasts-parchment-dim)",
          display: "inline-flex",
          fontSize: "0.64rem",
          gap: "0.4rem",
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          whiteSpace: "nowrap",
        }}
      >
        <LivePulse
          active={connected}
          color={
            tone === "currents"
              ? "var(--currents-gold)"
              : "var(--forecasts-cool-gold)"
          }
          label={connected ? "live" : label}
        />
      </div>
    </div>
  );
}

export default function DualPulseClient({
  initialForecasts,
  initialOpinions,
}: DualPulseClientProps) {
  const [activeTab, setActiveTab] = useState<ActiveTab>("currents");
  const initialOpinionIds = useRef(new Set(initialOpinions.map((item) => item.id)));
  const initialForecastIds = useRef(new Set(initialForecasts.map((item) => item.id)));
  const opinionsState = useLiveOpinions(initialOpinions);
  const forecastsState = useLiveForecasts(initialForecasts);

  const opinions = opinionsState.opinions.slice(0, WINDOW_SIZE);
  const forecasts = useMemo(
    () =>
      forecastsState.forecasts
        .map((forecast) => {
          const resolution = forecastsState.resolutions[forecast.id];
          return resolution && forecast.resolution?.id !== resolution.id
            ? { ...forecast, status: "RESOLVED", resolution }
            : forecast;
        })
        .slice(0, WINDOW_SIZE),
    [forecastsState.forecasts, forecastsState.resolutions],
  );

  if (opinions.length === 0 && forecasts.length === 0) {
    return (
      <section
        aria-labelledby="dual-pulse-title"
        className="dual-pulse-section"
        data-breakpoint-matrix="desktop>=1024 tablet=720-1023 mobile<720"
      >
        <div className="dual-pulse-heading">
          <p className="mono">Live public surface</p>
          <h2 id="dual-pulse-title">
            Theseus thinks out loud - what's happening, and what's about to.
          </h2>
        </div>
        <EmptyPane>
          Theseus is starting up - first opinion expected within the hour.
        </EmptyPane>
        <DualPulseStyles />
      </section>
    );
  }

  return (
    <section
      aria-labelledby="dual-pulse-title"
      className="dual-pulse-section"
      data-breakpoint-matrix="desktop>=1024 tablet=720-1023 mobile<720"
    >
      <div className="dual-pulse-heading">
        <p className="mono">Live public surface</p>
        <h2 id="dual-pulse-title">
          Theseus thinks out loud - what's happening, and what's about to.
        </h2>
      </div>

      <div aria-label="Pulse feed selector" className="dual-pulse-tabs">
        <button
          aria-pressed={activeTab === "currents"}
          onClick={() => setActiveTab("currents")}
          type="button"
        >
          Currents
        </button>
        <button
          aria-pressed={activeTab === "forecasts"}
          onClick={() => setActiveTab("forecasts")}
          type="button"
        >
          Forecasts
        </button>
      </div>

      <div className="dual-pulse-grid">
        <section
          aria-label="Currents live opinion window"
          className="dual-pulse-panel"
          data-active={activeTab === "currents"}
        >
          <PaneHeader
            connected={opinionsState.connected}
            label="reconnecting"
            title="CURRENTS - live opinion"
            tone="currents"
          />
          <div className="dual-pulse-scroll">
            {opinions.length ? (
              opinions.map((opinion) => (
                <OpinionCard
                  className={
                    initialOpinionIds.current.has(opinion.id)
                      ? undefined
                      : "currents-fade-in"
                  }
                  key={opinion.id}
                  opinion={opinion}
                />
              ))
            ) : (
              <EmptyPane>
                No live opinions yet. The Currents side will populate as soon
                as the source base supports a position.
              </EmptyPane>
            )}
          </div>
          <Link className="dual-pulse-link" href="/currents">
            view all currents -&gt;
          </Link>
        </section>

        <section
          aria-label="Forecasts live predictions window"
          className="dual-pulse-panel"
          data-active={activeTab === "forecasts"}
        >
          <PaneHeader
            connected={forecastsState.connected}
            label="reconnecting"
            title="FORECASTS - live predictions"
            tone="forecasts"
          />
          <div className="dual-pulse-scroll">
            {forecasts.length ? (
              forecasts.map((forecast) => (
                <ForecastCard
                  className={
                    initialForecastIds.current.has(forecast.id)
                      ? undefined
                      : "currents-fade-in"
                  }
                  forecast={forecast}
                  key={forecast.id}
                />
              ))
            ) : (
              <EmptyPane>
                No predictions yet - the model abstains until it has enough
                source-grounded evidence.
              </EmptyPane>
            )}
          </div>
          <Link className="dual-pulse-link" href="/forecasts">
            view all forecasts -&gt;
          </Link>
        </section>
      </div>

      <DualPulseStyles />
    </section>
  );
}

function DualPulseStyles() {
  return (
    <style>{`
      .dual-pulse-section {
        background: rgba(20, 18, 16, 0.86);
        border: 1px solid rgba(232, 225, 211, 0.14);
        border-radius: 6px;
        box-shadow: 0 16px 38px rgba(0, 0, 0, 0.2);
        margin-bottom: 2rem;
        padding: 0.9rem;
      }

      .dual-pulse-heading {
        margin: 0 0 0.9rem;
      }

      .dual-pulse-heading p {
        color: var(--amber-dim);
        font-size: 0.62rem;
        letter-spacing: 0.22em;
        margin: 0 0 0.3rem;
        text-transform: uppercase;
      }

      .dual-pulse-heading h2 {
        color: var(--parchment);
        font-family: 'EB Garamond', serif;
        font-size: clamp(1.25rem, 2.4vw, 1.85rem);
        letter-spacing: 0;
        line-height: 1.18;
        margin: 0;
      }

      .dual-pulse-tabs {
        display: flex;
        gap: 0.45rem;
        margin-bottom: 0.85rem;
      }

      .dual-pulse-tabs button {
        background: transparent;
        border: 1px solid rgba(232, 225, 211, 0.16);
        border-radius: 999px;
        color: var(--parchment-dim);
        cursor: pointer;
        flex: 1;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.66rem;
        letter-spacing: 0.12em;
        padding: 0.52rem 0.7rem;
        text-transform: uppercase;
      }

      .dual-pulse-tabs button[aria-pressed="true"] {
        background: rgba(212, 160, 23, 0.13);
        border-color: var(--currents-gold);
        color: var(--currents-gold);
      }

      .dual-pulse-grid {
        display: grid;
        grid-template-columns: minmax(0, 1fr);
      }

      .dual-pulse-panel {
        display: none;
        flex-direction: column;
        min-width: 0;
      }

      .dual-pulse-panel[data-active="true"] {
        display: flex;
      }

      .dual-pulse-scroll {
        display: grid;
        gap: 0.85rem;
        max-height: min(72vh, 42rem);
        overflow-y: auto;
        padding-right: 0.2rem;
      }

      .dual-pulse-link {
        align-self: flex-start;
        color: var(--currents-gold);
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.66rem;
        letter-spacing: 0.16em;
        margin-top: 0.85rem;
        text-decoration: none;
        text-transform: uppercase;
      }

      @media (min-width: 720px) {
        .dual-pulse-section {
          padding: 1rem;
        }

        .dual-pulse-tabs {
          display: none;
        }

        .dual-pulse-grid {
          grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
        }

        .dual-pulse-panel {
          display: flex;
          padding: 0 0.9rem;
        }

        .dual-pulse-panel:first-child {
          padding-left: 0;
        }

        .dual-pulse-panel + .dual-pulse-panel {
          border-left: 1px solid rgba(232, 225, 211, 0.12);
          padding-right: 0;
        }
      }

      @media (min-width: 1024px) {
        .dual-pulse-section {
          padding: 1.2rem;
        }

        .dual-pulse-panel {
          padding: 0 1.1rem;
        }
      }

      @media (max-width: 719px) {
        .dual-pulse-panel[data-active="false"] {
          display: none;
        }
      }
    `}</style>
  );
}
