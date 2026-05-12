"use client";

import { type CSSProperties, useEffect, useState } from "react";

interface LiveBannerProps {
  connected: boolean;
  /**
   * When true the banner explicitly distinguishes a stalled live feed from a
   * fresh page load. Public surfaces leave this false so a brief disconnect
   * reads as "live feed paused" rather than "reconnecting…".
   */
  diagnostic?: boolean;
}

const bannerStyle: CSSProperties = {
  alignItems: "center",
  border: "1px solid var(--currents-border)",
  borderRadius: "999px",
  color: "var(--currents-parchment-dim)",
  display: "inline-flex",
  fontSize: "0.74rem",
  gap: "0.45rem",
  letterSpacing: "0.06em",
  marginBottom: "1rem",
  padding: "0.32rem 0.7rem",
  textTransform: "uppercase",
};

const dotStyle: CSSProperties = {
  borderRadius: "50%",
  display: "inline-block",
  height: "6px",
  width: "6px",
};

const STALLED_AFTER_MS = 8_000;

export default function LiveBanner({
  connected,
  diagnostic = false,
}: LiveBannerProps) {
  const [stalled, setStalled] = useState(false);

  useEffect(() => {
    if (connected) {
      setStalled(false);
      return;
    }
    const handle = window.setTimeout(() => setStalled(true), STALLED_AFTER_MS);
    return () => window.clearTimeout(handle);
  }, [connected]);

  const label = connected
    ? "Live"
    : diagnostic
      ? stalled
        ? "Live feed disconnected"
        : "Connecting…"
      : "Live feed paused";

  return (
    <div aria-live="polite" style={bannerStyle}>
      <span
        className={connected ? "currents-pulse" : ""}
        style={{
          ...dotStyle,
          background: connected ? undefined : "var(--currents-muted)",
        }}
      />
      <span>{label}</span>
    </div>
  );
}
