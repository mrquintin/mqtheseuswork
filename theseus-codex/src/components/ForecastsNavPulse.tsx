"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import LivePulse from "@/app/forecasts/LivePulse";
import { useLiveForecasts } from "@/lib/useLiveForecasts";

export function ForecastsNavPulse({ label = "Forecasts" }: { label?: string }) {
  const pathname = usePathname();
  const active = pathname?.startsWith("/forecasts");
  const { connected } = useLiveForecasts([]);

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
      {connected ? (
        <LivePulse active color="var(--forecasts-cool-gold)" />
      ) : null}
    </Link>
  );
}
