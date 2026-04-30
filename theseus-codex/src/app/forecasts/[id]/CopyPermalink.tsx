"use client";

import { useState } from "react";

export function CopyPermalink({ forecastId }: { forecastId: string }) {
  const [copied, setCopied] = useState(false);

  const onClick = async () => {
    // Share permalinks intentionally have no UTM params, tracking pixels, or fingerprints.
    const url = `${window.location.origin}/forecasts/${encodeURIComponent(forecastId)}`;

    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      window.prompt("Copy this permalink:", url);
    }
  };

  return (
    <button
      type="button"
      aria-live="polite"
      onClick={onClick}
      style={{
        background: copied ? "rgba(196, 160, 75, 0.13)" : "transparent",
        border: "1px solid var(--forecasts-parchment-dim)",
        borderRadius: "999px",
        color: copied
          ? "var(--forecasts-cool-gold)"
          : "var(--forecasts-parchment-dim)",
        cursor: "pointer",
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: "0.68rem",
        letterSpacing: "0.08em",
        padding: "0.32rem 0.55rem",
        textTransform: "uppercase",
      }}
    >
      {copied ? "permalink copied" : "copy permalink"}
    </button>
  );
}
