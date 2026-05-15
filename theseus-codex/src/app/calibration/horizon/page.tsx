import type { Metadata } from "next";

import HorizonTab from "@/components/HorizonTab";
import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import { loadHorizonCalibration } from "@/lib/calibrationData";

export const metadata: Metadata = {
  title: "Calibration by Horizon",
  description:
    "How Theseus's forecast calibration varies by horizon. Per-bucket reliability with bootstrap CIs, the firm's empirically useful prediction horizon, and a method × horizon cross-tab — a single Brier hides all of this.",
  openGraph: {
    title: "Theseus Calibration — by Forecast Horizon",
    description:
      "A 7-day forecast and a 1-year forecast are different animals. Per-bucket Brier, calibration slope, and the firm's useful prediction horizon.",
    type: "website",
  },
};

export const dynamic = "force-dynamic";

type SearchParams = {
  domain?: string;
};

export default async function CalibrationHorizonPage({
  searchParams,
}: {
  searchParams?: Promise<SearchParams>;
}) {
  const founder = await getFounder();
  const params = (await searchParams) ?? {};
  const horizon = await loadHorizonCalibration({ domain: params.domain ?? null });

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main
        className="public-container public-calibration-page"
        style={{ padding: "2rem 1.5rem" }}
      >
        <HorizonTab horizon={horizon} />
      </main>
    </>
  );
}
