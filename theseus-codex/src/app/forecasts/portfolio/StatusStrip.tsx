import type { CSSProperties } from "react";

export type LiveTradingStatus = "DISABLED" | "ENABLED-AWAITING-AUTH" | "ENABLED";

interface StatusStripProps {
  killSwitchEngaged: boolean;
  killSwitchReason?: string | null;
  liveTradingAuthorized?: boolean | null;
  liveTradingEnabled?: boolean;
  liveTradingStatus?: string | null;
  updatedAt?: string | null;
}

const stripStyle: CSSProperties = {
  display: "grid",
  gap: "0.75rem",
  gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
};

function statusCardStyle(palette: "amber" | "green" | "muted" | "red"): CSSProperties {
  const color =
    palette === "red"
      ? "#b95c5c"
      : palette === "amber"
        ? "var(--forecasts-cool-gold)"
        : palette === "green"
          ? "var(--forecasts-prob-yes)"
          : "var(--forecasts-muted)";
  return {
    background: "rgba(232, 225, 211, 0.035)",
    border: `1px solid ${color}`,
    borderRadius: "8px",
    boxShadow: palette === "red" ? "0 0 0 1px rgba(185, 92, 92, 0.2)" : "none",
    padding: "0.85rem 1rem",
  };
}

function labelStyle(color: string): CSSProperties {
  return {
    color,
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: "0.78rem",
    letterSpacing: "0.08em",
    textTransform: "uppercase",
  };
}

export function liveTradingStatusFor({
  liveTradingAuthorized,
  liveTradingEnabled,
  liveTradingStatus,
}: Pick<StatusStripProps, "liveTradingAuthorized" | "liveTradingEnabled" | "liveTradingStatus">): LiveTradingStatus {
  const explicit = liveTradingStatus?.toUpperCase();
  if (
    explicit === "DISABLED" ||
    explicit === "ENABLED-AWAITING-AUTH" ||
    explicit === "ENABLED"
  ) {
    return explicit;
  }
  if (!liveTradingEnabled) return "DISABLED";
  return liveTradingAuthorized ? "ENABLED" : "ENABLED-AWAITING-AUTH";
}

function formatUpdatedAt(ts?: string | null): string | null {
  if (!ts) return null;
  const parsed = new Date(ts);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleString("en-US", {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
  });
}

export default function StatusStrip(props: StatusStripProps) {
  const liveStatus = liveTradingStatusFor(props);
  const livePalette =
    liveStatus === "ENABLED" ? "green" : liveStatus === "ENABLED-AWAITING-AUTH" ? "amber" : "muted";
  const killSwitchPalette = props.killSwitchEngaged ? "red" : "green";
  const updatedAt = formatUpdatedAt(props.updatedAt);

  return (
    <section aria-label="Portfolio operating status" style={stripStyle}>
      <div data-live-status={liveStatus} data-live-status-palette={livePalette} style={statusCardStyle(livePalette)}>
        <div style={labelStyle(livePalette === "muted" ? "var(--forecasts-muted)" : "var(--forecasts-cool-gold)")}>
          Live trading
        </div>
        <div style={{ color: "var(--forecasts-parchment)", fontSize: "1rem", marginTop: "0.35rem" }}>
          {liveStatus}
        </div>
        <p style={{ color: "var(--forecasts-parchment-dim)", fontSize: "0.82rem", margin: "0.35rem 0 0" }}>
          {liveStatus === "DISABLED"
            ? "Public scoreboard is paper-only."
            : liveStatus === "ENABLED-AWAITING-AUTH"
              ? "Live mode is available, but founder authorization is still required before execution."
              : "Live mode is enabled; operator-only details remain behind founder login."}
        </p>
      </div>

      <div
        data-kill-switch={props.killSwitchEngaged ? "ENGAGED" : "clear"}
        data-kill-switch-palette={killSwitchPalette}
        style={statusCardStyle(killSwitchPalette)}
      >
        <div style={labelStyle(props.killSwitchEngaged ? "#b95c5c" : "var(--forecasts-prob-yes)")}>
          Kill switch
        </div>
        <div style={{ color: "var(--forecasts-parchment)", fontSize: "1rem", marginTop: "0.35rem" }}>
          {props.killSwitchEngaged ? "ENGAGED" : "clear"}
        </div>
        <p style={{ color: "var(--forecasts-parchment-dim)", fontSize: "0.82rem", margin: "0.35rem 0 0" }}>
          {props.killSwitchEngaged
            ? props.killSwitchReason || "Trading has paused itself."
            : "No automatic trading halt is active."}
          {updatedAt ? ` Updated ${updatedAt}.` : ""}
        </p>
      </div>
    </section>
  );
}
