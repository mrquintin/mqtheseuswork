"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function ForecastsNavPulse({ label = "Forecasts" }: { label?: string }) {
  const pathname = usePathname();
  const active = pathname?.startsWith("/forecasts");

  return (
    <Link
      href="/forecasts"
      aria-label="Forecasts - live predictions"
      style={{
        alignItems: "center",
        color: active ? "var(--forecasts-cool-gold)" : "var(--amber-dim)",
        display: "inline-flex",
        fontWeight: active ? 600 : undefined,
        gap: "0.35rem",
        textDecoration: "none",
      }}
    >
      {label}
      <span aria-hidden className="currents-pulse" />
    </Link>
  );
}
