import { permanentRedirect } from "next/navigation";

/**
 * `/forecasts/portfolio` was the prediction-market-only portfolio. As of
 * the unified-portfolio rollout, that surface is one tab inside the
 * firm-wide `/portfolio` page. The matching permanent redirect in
 * `next.config.ts` handles most requests; this page-level redirect is
 * the belt-and-suspenders fallback so any request that bypasses the
 * config-level rule still lands at the canonical page.
 */
export default function ForecastsPortfolioRedirect(): never {
  permanentRedirect("/portfolio");
}
