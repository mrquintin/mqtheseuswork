"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Load-bearing public Currents affordance. It is intentionally backend-free:
 * the gold pulse advertises the live surface even when the SSE service is down.
 */
export function CurrentsNavPulse({ label = "Current events" }: { label?: string } = {}) {
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
        color: active ? "var(--currents-gold)" : "var(--amber-dim)",
        fontWeight: active ? 600 : undefined,
        textDecoration: "none",
      }}
    >
      {label}
      <span aria-hidden className="currents-pulse" />
    </Link>
  );
}
