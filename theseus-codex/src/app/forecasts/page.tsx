import type { Metadata } from "next";

import ForecastGridClient from "@/app/forecasts/ForecastGridClient";
import { listForecasts } from "@/lib/forecastsApi";
import type { PublicForecast } from "@/lib/forecastsTypes";
import { SITE } from "@/lib/site";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const SEED_FETCH_TIMEOUT_MS = 8_000;

function meanBrierDescription(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "Live predictions from Theseus, source-grounded and scored as markets resolve.";
  }
  return `Live predictions from Theseus. Mean Brier 90d: ${value.toFixed(3)}.`;
}

export async function generateMetadata(): Promise<Metadata> {
  const title = "Theseus — Forecasts";
  const description = meanBrierDescription(null);

  return {
    title,
    description,
    openGraph: {
      description,
      images: [
        {
          alt: "Theseus Forecasts",
          height: 630,
          url: `${SITE}/api/og/forecasts`,
          width: 1200,
        },
      ],
      siteName: "Theseus Codex",
      title,
      type: "website",
      url: `${SITE}/forecasts`,
    },
    twitter: {
      card: "summary_large_image",
      description,
      images: [`${SITE}/api/og/forecasts`],
      title,
    },
  };
}

export default async function ForecastsPage() {
  let seed: PublicForecast[] = [];

  try {
    const resp = await listForecasts(
      { limit: 20, seeded: true },
      { cache: "no-store", timeoutMs: SEED_FETCH_TIMEOUT_MS },
    );
    seed = Array.isArray(resp.items) ? resp.items : [];
  } catch (err) {
    console.error("forecasts_seed_fetch_failed", err);
  }

  return <ForecastGridClient seed={seed} />;
}
