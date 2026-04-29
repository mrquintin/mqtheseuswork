"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Load-bearing public Currents affordance. It is intentionally backend-free:
 * the gold pulse advertises the live surface even when the SSE service is down.
 */
export function CurrentsNavPulse() {
  const pathname = usePathname();
  const active = pathname?.startsWith("/currents");

  return (
    <Link
      href="/currents"
      aria-label="Current events — live"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.35rem",
        color: active ? "var(--currents-gold)" : undefined,
        fontWeight: active ? 600 : undefined,
        textDecoration: "none",
      }}
    >
      Current events
      <span aria-hidden className="currents-pulse" />
    </Link>
  );
}
