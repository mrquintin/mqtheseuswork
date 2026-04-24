"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

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
        color: active ? "#d4a017" : undefined,
        fontWeight: active ? 600 : undefined,
      }}
    >
      Current events
      <span
        aria-hidden
        style={{
          display: "inline-block",
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: "#d4a017",
          boxShadow: "0 0 8px rgba(212, 160, 23, 0.55)",
          animation: "currents-pulse 1.8s ease-in-out infinite",
        }}
      />
    </Link>
  );
}
