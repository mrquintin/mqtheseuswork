import type { Metadata } from "next";

import { getForecastPortfolioSurface } from "@/lib/forecastPortfolioData";
import { SITE } from "@/lib/site";
import { requireTenantContext } from "@/lib/tenant";

import { addWatchedMarket } from "./actions";
import ForecastPortfolioView from "./ForecastPortfolioView";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

export const metadata: Metadata = {
  title: "Theseus - Forecasts portfolio",
  description: "Paper prediction-market positions, forecast traces, and live-trading gate state.",
  openGraph: {
    description: "Paper prediction-market positions, forecast traces, and live-trading gate state.",
    siteName: "Theseus Codex",
    title: "Theseus - Forecasts portfolio",
    type: "website",
    url: `${SITE}/forecasts/portfolio`,
  },
};

function firstParam(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
}

function watchState(value: string | null): "added" | "invalid" | "unsupported" | null {
  if (value === "added" || value === "invalid" || value === "unsupported") return value;
  return null;
}

export default async function ForecastsPortfolioPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const params = await searchParams;
  const surface = await getForecastPortfolioSurface(tenant.organizationId);

  return (
    <ForecastPortfolioView
      addWatchedMarketAction={addWatchedMarket}
      surface={surface}
      watchState={watchState(firstParam(params.watch))}
    />
  );
}
