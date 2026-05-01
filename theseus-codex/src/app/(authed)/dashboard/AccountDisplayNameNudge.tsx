"use client";

import Link from "next/link";
import { useState } from "react";

const NUDGE_COPY =
  "Set your display name on /account so your peers see something meaningful.";

export default function AccountDisplayNameNudge() {
  const [visible, setVisible] = useState(true);
  const [busy, setBusy] = useState(false);

  if (!visible) return null;

  async function dismiss() {
    setBusy(true);
    try {
      const res = await fetch("/api/account/nudge", { method: "PATCH" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setVisible(false);
    } catch {
      setBusy(false);
    }
  }

  return (
    <div
      role="status"
      className="portal-card"
      style={{
        marginBottom: "1rem",
        padding: "0.75rem 0.9rem",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "1rem",
        border: "1px solid var(--amber)",
      }}
    >
      <Link
        href="/account"
        style={{
          color: "var(--amber)",
          fontSize: "0.85rem",
          textDecoration: "none",
        }}
      >
        {NUDGE_COPY}
      </Link>
      <button
        type="button"
        className="mono"
        onClick={() => void dismiss()}
        disabled={busy}
        aria-label="Dismiss display name reminder"
        style={{
          background: "transparent",
          border: "1px solid var(--amber-dim)",
          borderRadius: 2,
          color: "var(--parchment-dim)",
          cursor: busy ? "wait" : "pointer",
          fontSize: "0.58rem",
          letterSpacing: "0.18em",
          padding: "0.25rem 0.5rem",
          textTransform: "uppercase",
        }}
      >
        Dismiss
      </button>
    </div>
  );
}
