import type { NextConfig } from "next";

// `output: "standalone"` is useful for Docker (self-contained server.js with
// trimmed node_modules) but actively harmful on Vercel — Vercel's build
// pipeline expects the default output and will reject the standalone tree
// with confusing "function.json is invalid" errors.
//
// Detection: Vercel sets VERCEL=1 in every build. We also skip standalone when
// running locally (`next dev`) because it's only a production-build concern.
const isVercel = process.env.VERCEL === "1" || !!process.env.VERCEL_URL;

export const legacyNavRedirects = [
  { source: "/conclusions", destination: "/knowledge?tab=conclusions", permanent: false },
  { source: "/explorer", destination: "/knowledge?tab=explorer", permanent: false },
  { source: "/library", destination: "/knowledge?tab=library", permanent: false },
  {
    source: "/publication",
    destination: "/knowledge?tab=conclusions&notice=publication-retired",
    permanent: false,
  },
  { source: "/peer-review", destination: "/ops?panel=peer-review", permanent: false },
  {
    source: "/peer-review/:path*",
    destination: "/ops?panel=peer-review&target=:path*",
    permanent: false,
  },
  { source: "/contradictions", destination: "/ops?panel=contradictions", permanent: false },
  { source: "/post-mortem", destination: "/ops?panel=post-mortem", permanent: false },
  { source: "/adversarial", destination: "/ops?panel=adversarial", permanent: false },
  { source: "/decay", destination: "/ops?panel=decay", permanent: false },
  { source: "/rigor-gate", destination: "/ops?panel=rigor-gate", permanent: false },
  {
    source: "/rigor-gate/:path*",
    destination: "/ops?panel=rigor-gate&target=:path*",
    permanent: false,
  },
  { source: "/open-questions", destination: "/ops?panel=open-questions", permanent: false },
  { source: "/q/review", destination: "/ops?panel=layer-review", permanent: false },
  { source: "/scoreboard", destination: "/ops?panel=calibration", permanent: false },
] as const;

export const retiredPublicRouteRedirects = [
  { source: "/responses", destination: "/", permanent: true },
  // Round 24 prompt 63: the forecasts portfolio is now one tab inside the
  // unified `/portfolio` surface. Old URL is preserved as a permanent
  // redirect so any deep link still resolves.
  { source: "/forecasts/portfolio", destination: "/portfolio", permanent: true },
] as const;

export const appRedirects = [
  ...retiredPublicRouteRedirects,
  ...legacyNavRedirects,
] as const;

const nextConfig: NextConfig = {
  ...(isVercel ? {} : { output: "standalone" }),
  // Drop the server-identification header — it adds nothing useful and
  // costs ~30 bytes per response. The compress: true default stays.
  poweredByHeader: false,
  // Build-time source maps for the client bundle are off in production
  // (and were never on; making it explicit prevents an accidental flag
  // flip from doubling the deployed asset size).
  productionBrowserSourceMaps: false,
  async redirects() {
    return [...appRedirects];
  },
  experimental: {
    serverActions: {
      // Audio / PDF uploads routed through server actions; API route uploads
      // are still capped at Vercel's 4.5 MB serverless-request limit, so
      // large files must use direct-to-storage uploads (pre-signed URLs).
      bodySizeLimit: "50mb",
    },
    // Tree-shake icon + utility packages that ship a deep module tree.
    // Without this, importing a single `lucide-react` icon pulls the
    // whole icon set into the client chunk; `optimizePackageImports`
    // rewrites the import so only the named export survives bundling.
    // Documented in https://nextjs.org/docs/app/api-reference/next-config-js/optimizePackageImports.
    optimizePackageImports: ["lucide-react"],
  },
};

export default nextConfig;
