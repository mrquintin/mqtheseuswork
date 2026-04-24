import type { NextConfig } from "next";

// Hybrid build target:
//   - unset (default): regular Next.js server build supporting route handlers (/api/currents/*).
//   - "standalone":    containerized deploys (Docker/self-hosted).
//   - "export":        legacy fully-static export (route handlers will NOT work).
const buildTarget = process.env.NEXT_BUILD_TARGET;

const nextConfig: NextConfig = {
  output:
    buildTarget === "standalone"
      ? "standalone"
      : buildTarget === "export"
        ? "export"
        : undefined,
  images: { unoptimized: true },
};

export default nextConfig;
