"use client";

import { useState } from "react";

export function CopyLinkButton({ opinionId }: { opinionId: string }) {
  const [copied, setCopied] = useState(false);
  const onClick = async () => {
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
      onClick={onClick}
      style={{
        background: "transparent",
        border: "1px solid var(--currents-border)",
        color: "var(--currents-parchment-dim)",
        padding: "0.32rem 0.6rem",
        fontSize: "0.75rem",
        borderRadius: 2,
        cursor: "pointer",
        letterSpacing: "0.04em",
      }}
    >
      {copied ? "permalink copied" : "copy permalink"}
    </button>
  );
}
