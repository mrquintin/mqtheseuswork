"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const NUDGE_COPY =
  "Set your display name on /account so your peers see something meaningful.";

// R-014: a long-lived client-side dismissal key. Server-side gate
// already suppresses the nudge once `accountNudgeDismissedAt` is set,
// but if the founder's display name happens to equal their email
// local-part the server gate can flap; this cookie is the belt to the
// server's braces. Expires in 90 days so a genuine renamed-account
// flow can re-surface the nudge.
const DISMISS_COOKIE = "theseus_dismissed_display_name_nudge_at";
const DISMISS_TTL_DAYS = 90;

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${name}=`;
  const match = document.cookie
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(prefix));
  return match ? decodeURIComponent(match.slice(prefix.length)) : null;
}

function writeCookie(name: string, value: string, days: number) {
  if (typeof document === "undefined") return;
  const expires = new Date(Date.now() + days * 86_400_000).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

export default function AccountDisplayNameNudge() {
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setVisible(readCookie(DISMISS_COOKIE) === null);
  }, []);

  if (!visible) return null;

  async function dismiss() {
    setBusy(true);
    try {
      const res = await fetch("/api/account/nudge", { method: "PATCH" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      writeCookie(DISMISS_COOKIE, new Date().toISOString(), DISMISS_TTL_DAYS);
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
