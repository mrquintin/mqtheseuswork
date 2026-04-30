import DualPulseClient from "@/app/(home)/DualPulseClient";
import { listCurrents } from "@/lib/currentsApi";
import type { PublicOpinion } from "@/lib/currentsTypes";
import { listForecasts } from "@/lib/forecastsApi";
import type { PublicForecast } from "@/lib/forecastsTypes";

export const DUAL_PULSE_BREAKPOINT_MATRIX = {
  desktop: ">=1024px: two equal columns with a vertical rule",
  mobile: "<720px: stacked, tab toggle visible, Currents first",
  tablet: "720-1023px: two equal columns with narrower padding and the rule kept",
} as const;

async function seedOpinions(): Promise<PublicOpinion[]> {
  try {
    const response = await listCurrents({ limit: 4, seeded: true });
    return Array.isArray(response.items) ? response.items : [];
  } catch (error) {
    console.error("dual_pulse_currents_seed_failed", error);
    return [];
  }
}

async function seedForecasts(): Promise<PublicForecast[]> {
  try {
    const response = await listForecasts({ limit: 4, seeded: true });
    return Array.isArray(response.items) ? response.items : [];
  } catch (error) {
    console.error("dual_pulse_forecasts_seed_failed", error);
    return [];
  }
}

export default async function DualPulseSection() {
  const [initialOpinions, initialForecasts] = await Promise.all([
    seedOpinions(),
    seedForecasts(),
  ]);

  return (
    <DualPulseClient
      initialForecasts={initialForecasts}
      initialOpinions={initialOpinions}
    />
  );
}
