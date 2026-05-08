import type { CSSProperties } from "react";

interface LiveBannerProps {
  connected: boolean;
}

const bannerStyle: CSSProperties = {
  alignItems: "center",
  border: "1px solid var(--currents-border)",
  borderRadius: "999px",
  color: "var(--currents-parchment-dim)",
  display: "inline-flex",
  fontSize: "0.78rem",
  gap: "0.45rem",
  letterSpacing: "0.06em",
  marginBottom: "1rem",
  padding: "0.4rem 0.7rem",
  textTransform: "uppercase",
};

const dotStyle: CSSProperties = {
  borderRadius: "50%",
  display: "inline-block",
  height: "6px",
  width: "6px",
};

export default function LiveBanner({ connected }: LiveBannerProps) {
  return (
    <div aria-live="polite" style={bannerStyle}>
      <span
        className={connected ? "currents-pulse" : ""}
        style={{
          ...dotStyle,
          background: connected ? undefined : "var(--currents-muted)",
        }}
      />
      <span>{connected ? "live" : "reconnecting…"}</span>
    </div>
  );
}
