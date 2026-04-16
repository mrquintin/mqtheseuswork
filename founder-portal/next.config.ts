import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Allow file uploads up to 50MB
  experimental: {
    serverActions: {
      bodySizeLimit: "50mb",
    },
  },
};

export default nextConfig;
