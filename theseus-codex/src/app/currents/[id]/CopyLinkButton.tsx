"use client";

import { useState } from "react";

export function CopyLinkButton({ opinionId }: { opinionId: string }) {
  const [copied, setCopied] = useState(false);

  const onClick = async () => {
    // Share permalinks intentionally have no UTM params, tracking pixels, or fingerprints.
    const url = `${window.location.origin}/currents/${encodeURIComponent(opinionId)}`;

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
      className="currents-copy-link-button"
      onClick={onClick}
      style={{
        background: copied ? "rgba(212, 160, 23, 0.12)" : "transparent",
        border: "1px solid var(--currents-parchment-dim)",
        borderRadius: "999px",
        color: copied ? "var(--currents-gold)" : "var(--currents-parchment-dim)",
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
