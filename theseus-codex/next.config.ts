import type { NextConfig } from "next";

// `output: "standalone"` is useful for Docker (self-contained server.js with
// trimmed node_modules) but actively harmful on Vercel — Vercel's build
// pipeline expects the default output and will reject the standalone tree
// with confusing "function.json is invalid" errors.
//
// Detection: Vercel sets VERCEL=1 in every build. We also skip standalone when
// running locally (`next dev`) because it's only a production-build concern.
const isVercel = process.env.VERCEL === "1" || !!process.env.VERCEL_URL;

const nextConfig: NextConfig = {
  ...(isVercel ? {} : { output: "standalone" }),
  experimental: {
    serverActions: {
      // Audio / PDF uploads routed through server actions; API route uploads
      // are still capped at Vercel's 4.5 MB serverless-request limit, so
      // large files must use direct-to-storage uploads (pre-signed URLs).
      bodySizeLimit: "50mb",
    },
  },
};

export default nextConfig;
