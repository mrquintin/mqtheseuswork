"use client";

import { useEffect, useState } from "react";
import { relativeTime } from "@/lib/relativeTime";

export function LiveBanner({
  connected,
  lastOpinionAt,
}: {
  connected: boolean;
  lastOpinionAt: string | null;
}) {
  // Refresh the "last update Xm ago" copy periodically.
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div
      data-testid="live-banner"
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.55rem",
        padding: "0.4rem 0.75rem",
        margin: "1rem 0 1.25rem",
        border: "1px solid var(--currents-border)",
        borderRadius: "999px",
        background: "var(--currents-bg-elevated)",
        width: "fit-content",
        fontSize: "0.78rem",
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: connected
          ? "var(--currents-gold)"
          : "var(--currents-parchment-dim)",
      }}
    >
      <span
        aria-hidden
        className={connected ? "currents-pulse" : ""}
        style={
          connected
            ? undefined
            : {
                display: "inline-block",
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                background: "var(--currents-muted)",
                opacity: 0.6,
              }
        }
      />
      <span>{connected ? "live" : "reconnecting…"}</span>
      {lastOpinionAt ? (
        <span
          style={{
            color: "var(--currents-parchment-dim)",
            textTransform: "none",
            letterSpacing: "0.02em",
            fontSize: "0.75rem",
          }}
        >
          · last update {relativeTime(lastOpinionAt)}
        </span>
      ) : null}
    </div>
  );
}
