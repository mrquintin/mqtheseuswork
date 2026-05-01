import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

import type {
  ForecastPortfolioSurface,
  PipelineCandidateRow,
  PortfolioMode,
  PortfolioPositionRow,
  ResolvedPositionRow,
  TraceGateResult,
  TracePrinciple,
  WatchingState,
} from "@/lib/forecastPortfolioData";

type WatchState = "added" | "invalid" | "unsupported" | null;

type ForecastPortfolioViewProps = {
  addWatchedMarketAction?: (formData: FormData) => void | Promise<void>;
  surface: ForecastPortfolioSurface;
  watchState?: WatchState;
};

const sectionStyle: CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 6,
  background: "rgba(232, 225, 211, 0.035)",
  padding: "1rem",
};

const tableWrapStyle: CSSProperties = {
  border: "1px solid rgba(232, 225, 211, 0.12)",
  borderRadius: 6,
  overflowX: "auto",
};

const tableStyle: CSSProperties = {
  borderCollapse: "collapse",
  minWidth: "920px",
  width: "100%",
};

const thStyle: CSSProperties = {
  borderBottom: "1px solid rgba(232, 225, 211, 0.14)",
  color: "var(--amber-dim)",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.62rem",
  letterSpacing: "0.16em",
  padding: "0.7rem",
  textAlign: "left",
  textTransform: "uppercase",
};

const tdStyle: CSSProperties = {
  borderBottom: "1px solid rgba(232, 225, 211, 0.08)",
  color: "var(--parchment)",
  fontSize: "0.86rem",
  padding: "0.72rem",
  verticalAlign: "top",
};

function modeColor(mode: PortfolioMode): string {
  if (mode === "PAPER") return "rgba(127, 196, 143, 0.92)";
  if (mode === "LIVE") return "var(--amber)";
  return "var(--ember)";
}

function formatUsd(value: number): string {
  const out = new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
    style: "currency",
  }).format(Math.abs(value));
  return value < 0 ? `-${out}` : value > 0 ? `+${out}` : out;
}

function formatUnsignedUsd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
    style: "currency",
  }).format(value);
}

function formatPercent(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "n/a";
  return `${Math.round(value * 1000) / 10}%`;
}

function formatNumber(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "n/a";
  return value.toFixed(3);
}

function formatDate(value: Date | string | null): string {
  if (!value) return "n/a";
  const parsed = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(parsed.getTime())) return "n/a";
  return parsed.toLocaleString("en-US", {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
  });
}

function SectionTitle({ children, id }: { children: ReactNode; id: string }) {
  return (
    <h2
      id={id}
      style={{
        color: "var(--amber)",
        fontFamily: "'Cinzel', serif",
        fontSize: "1.05rem",
        letterSpacing: "0.06em",
        margin: 0,
      }}
    >
      {children}
    </h2>
  );
}

function PrincipleChips({ principles }: { principles: TracePrinciple[] }) {
  if (principles.length === 0) {
    return <span style={{ color: "var(--parchment-dim)" }}>No trace yet</span>;
  }
  return (
    <span style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
      {principles.map((principle) => (
        <Link
          key={principle.conclusionId}
          data-testid="forecast-principle-chip"
          href={`/conclusions/${principle.conclusionId}`}
          title={principle.snippet || principle.conclusionId}
          style={{
            border: "1px solid rgba(205, 151, 67, 0.45)",
            borderRadius: 4,
            color: "var(--amber)",
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "0.68rem",
            padding: "0.16rem 0.36rem",
            textDecoration: "none",
          }}
        >
          [C:{principle.conclusionId.slice(0, 8)}]
        </Link>
      ))}
    </span>
  );
}

function FailedGates({ gates }: { gates: TraceGateResult[] }) {
  const failed = gates.filter((gate) => !gate.passed);
  if (failed.length === 0) return null;
  return (
    <ul style={{ color: "var(--ember)", margin: "0.6rem 0 0", paddingLeft: "1.1rem" }}>
      {failed.map((gate) => (
        <li key={gate.gateName}>
          <span className="mono">{gate.gateName}</span>: {gate.reason}
        </li>
      ))}
    </ul>
  );
}

function ModeBanner({ surface }: { surface: ForecastPortfolioSurface }) {
  const accent = modeColor(surface.mode.mode);
  return (
    <section
      aria-labelledby="forecast-mode-heading"
      data-testid="forecast-mode-banner"
      style={{
        border: `1px solid ${accent}`,
        borderRadius: 6,
        background:
          surface.mode.mode === "GATE-BLOCKED"
            ? "rgba(172, 54, 37, 0.10)"
            : surface.mode.mode === "PAPER"
              ? "rgba(95, 126, 93, 0.12)"
              : "rgba(205, 151, 67, 0.10)",
        padding: "1rem",
      }}
    >
      <div style={{ alignItems: "start", display: "flex", gap: "1rem", justifyContent: "space-between", flexWrap: "wrap" }}>
        <div>
          <p className="mono" style={{ color: accent, fontSize: "0.68rem", letterSpacing: "0.22em", margin: 0, textTransform: "uppercase" }}>
            Current mode
          </p>
          <h1 id="forecast-mode-heading" style={{ color: accent, fontFamily: "'Cinzel Decorative', 'Cinzel', serif", margin: "0.2rem 0 0" }}>
            {surface.mode.mode}
          </h1>
        </div>
        <div className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.72rem", lineHeight: 1.7, maxWidth: "34rem" }}>
          <div>paper: conclusions - forecast trace - PaperBetEngine - paper ledger</div>
          <div>live: conclusions - forecast trace - safety.check_all_gates - live engine</div>
        </div>
      </div>
      <FailedGates gates={surface.mode.failedGates} />
    </section>
  );
}

function KpiStrip({ surface }: { surface: ForecastPortfolioSurface }) {
  const items = [
    ["Open positions", String(surface.kpis.openPositions)],
    ["Realized P&L (paper)", formatUsd(surface.kpis.realizedPaperPnl)],
    ["Unrealized P&L (paper)", formatUsd(surface.kpis.unrealizedPaperPnl)],
    ["Brier score", formatNumber(surface.kpis.runningBrier)],
    ["Hit rate", formatPercent(surface.kpis.hitRate)],
  ];
  return (
    <section aria-label="Forecast position summary" style={{ display: "grid", gap: "0.75rem", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
      {items.map(([label, value]) => (
        <div key={label} style={sectionStyle}>
          <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.6rem", letterSpacing: "0.15em", margin: 0, textTransform: "uppercase" }}>
            {label}
          </p>
          <strong style={{ color: "var(--parchment)", display: "block", fontSize: "1.35rem", marginTop: "0.3rem" }}>
            {value}
          </strong>
        </div>
      ))}
    </section>
  );
}

function OpenPositionsTable({ rows }: { rows: PortfolioPositionRow[] }) {
  return (
    <section aria-labelledby="open-positions-heading" style={sectionStyle}>
      <SectionTitle id="open-positions-heading">Open positions</SectionTitle>
      <div style={{ ...tableWrapStyle, marginTop: "0.85rem" }}>
        <table style={tableStyle}>
          <thead>
            <tr>
              {["Market", "Side", "Size", "Avg price", "Current implied prob", "Driving principles", "Last updated"].map((label) => (
                <th key={label} style={thStyle}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7} style={tdStyle}>No open paper or live positions.</td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.betId} data-testid="forecast-position-row">
                  <td style={tdStyle}>
                    {row.marketUrl ? (
                      <a href={row.marketUrl} rel="noreferrer" target="_blank" style={{ color: "var(--amber)", textDecoration: "none" }}>
                        {row.marketTitle}
                      </a>
                    ) : (
                      row.marketTitle
                    )}
                    <div className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.62rem", marginTop: "0.25rem" }}>
                      {row.mode} / {row.predictionId.slice(0, 8)}
                    </div>
                  </td>
                  <td style={tdStyle}>{row.side}</td>
                  <td style={tdStyle}>{formatUnsignedUsd(row.sizeUsd)}</td>
                  <td style={tdStyle}>{row.avgPrice.toFixed(3)}</td>
                  <td style={tdStyle}>{formatPercent(row.currentImpliedProb)}</td>
                  <td style={tdStyle}><PrincipleChips principles={row.drivingPrinciples} /></td>
                  <td style={tdStyle}>{formatDate(row.lastUpdated)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ResolvedTable({ rows }: { rows: ResolvedPositionRow[] }) {
  return (
    <section aria-labelledby="recently-resolved-heading" style={sectionStyle}>
      <SectionTitle id="recently-resolved-heading">Recently resolved</SectionTitle>
      <div style={{ ...tableWrapStyle, marginTop: "0.85rem" }}>
        <table style={tableStyle}>
          <thead>
            <tr>
              {["Market", "Outcome", "Our side", "P&L", "Reasoning"].map((label) => (
                <th key={label} style={thStyle}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={5} style={tdStyle}>No resolved positions yet.</td></tr>
            ) : (
              rows.map((row) => (
                <tr key={row.betId}>
                  <td style={tdStyle}>{row.marketTitle}<div className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.62rem" }}>{formatDate(row.resolvedAt)}</div></td>
                  <td style={tdStyle}>{row.outcome}</td>
                  <td style={tdStyle}>{row.ourSide}</td>
                  <td style={tdStyle}>{row.pnlUsd === null ? "n/a" : formatUsd(row.pnlUsd)}</td>
                  <td style={tdStyle}>
                    <Link href={row.reasoningHref} style={{ color: "var(--amber)", textDecoration: "none" }}>
                      Forecast notes
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PipelinePanel({ rows }: { rows: PipelineCandidateRow[] }) {
  return (
    <section aria-labelledby="pipeline-heading" style={sectionStyle}>
      <SectionTitle id="pipeline-heading">Pipeline</SectionTitle>
      <div style={{ display: "grid", gap: "0.75rem", marginTop: "0.85rem" }}>
        {rows.length === 0 ? (
          <p style={{ color: "var(--parchment-dim)", margin: 0 }}>No candidate markets are queued.</p>
        ) : (
          rows.map((row) => (
            <article key={row.marketId} style={{ border: "1px solid rgba(232, 225, 211, 0.12)", borderRadius: 6, padding: "0.85rem" }}>
              <div style={{ display: "flex", gap: "1rem", justifyContent: "space-between", flexWrap: "wrap" }}>
                <div>
                  <strong style={{ color: "var(--parchment)" }}>{row.marketTitle}</strong>
                  <div className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.62rem", marginTop: "0.2rem" }}>
                    {row.source}{row.category ? ` / ${row.category}` : ""} / {formatDate(row.lastUpdated)}
                  </div>
                </div>
                <span className="mono" style={{ color: row.gateResults.some((gate) => !gate.passed) ? "var(--ember)" : "rgba(127, 196, 143, 0.92)", fontSize: "0.66rem" }}>
                  {row.gateState}
                </span>
              </div>
              <div style={{ marginTop: "0.65rem" }}>
                <PrincipleChips principles={row.drivingPrinciples} />
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function WatchingPanel({
  action,
  state,
  watchState,
}: {
  action?: (formData: FormData) => void | Promise<void>;
  state: WatchingState;
  watchState: WatchState;
}) {
  const message =
    watchState === "added"
      ? "Market added to the watched queue."
      : watchState === "invalid"
        ? "Enter a valid Polymarket or Kalshi URL."
        : watchState === "unsupported"
          ? "Only Polymarket and Kalshi URLs are accepted."
          : null;
  return (
    <section aria-labelledby="watching-heading" style={sectionStyle}>
      <SectionTitle id="watching-heading">Watching</SectionTitle>
      <div style={{ display: "grid", gap: "0.85rem", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", marginTop: "0.85rem" }}>
        <div>
          <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.64rem", letterSpacing: "0.16em", margin: 0, textTransform: "uppercase" }}>
            Categories
          </p>
          <p style={{ color: "var(--parchment)", margin: "0.4rem 0 0" }}>
            Polymarket: {state.polymarketCategories.join(", ") || "none configured"}
          </p>
          <p style={{ color: "var(--parchment)", margin: "0.25rem 0 0" }}>
            Kalshi: {state.kalshiCategories.join(", ") || "none configured"}
          </p>
          <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.68rem", margin: "0.55rem 0 0" }}>
            scanned_this_week={state.scannedThisWeek}
          </p>
        </div>
        <form action={action} style={{ display: "grid", gap: "0.5rem" }}>
          <label className="mono" htmlFor="marketUrl" style={{ color: "var(--amber-dim)", fontSize: "0.64rem", letterSpacing: "0.16em", textTransform: "uppercase" }}>
            Ad-hoc market URL
          </label>
          <input
            id="marketUrl"
            name="marketUrl"
            placeholder="https://polymarket.com/event/..."
            style={{
              background: "rgba(0,0,0,0.25)",
              border: "1px solid var(--border)",
              borderRadius: 4,
              color: "var(--parchment)",
              padding: "0.65rem",
            }}
            type="url"
          />
          <button className="btn btn-solid" type="submit" style={{ justifySelf: "start" }}>
            Add market
          </button>
          {message ? <p role="status" style={{ color: watchState === "added" ? "rgba(127, 196, 143, 0.92)" : "var(--ember)", margin: 0 }}>{message}</p> : null}
        </form>
      </div>
      {state.watchedMarkets.length > 0 ? (
        <ul style={{ color: "var(--parchment-dim)", margin: "0.9rem 0 0", paddingLeft: "1.1rem" }}>
          {state.watchedMarkets.slice(0, 5).map((row) => (
            <li key={row.id}>
              <span className="mono">{row.source}</span> / <a href={row.url} rel="noreferrer" target="_blank" style={{ color: "var(--amber)" }}>{row.url}</a>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export default function ForecastPortfolioView({
  addWatchedMarketAction,
  surface,
  watchState = null,
}: ForecastPortfolioViewProps) {
  return (
    <main style={{ display: "grid", gap: "1rem", margin: "0 auto", maxWidth: 1180, padding: "1.5rem 1rem 3rem" }}>
      <ModeBanner surface={surface} />
      <KpiStrip surface={surface} />
      <OpenPositionsTable rows={surface.openPositions} />
      <ResolvedTable rows={surface.recentlyResolved} />
      <PipelinePanel rows={surface.pipeline} />
      <WatchingPanel action={addWatchedMarketAction} state={surface.watching} watchState={watchState} />
    </main>
  );
}
