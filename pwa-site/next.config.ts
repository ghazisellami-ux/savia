import type { NextConfig } from "next";

const BACKEND = process.env.BACKEND_URL || "http://backend:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  basePath: "/site",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND}/api/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "public, max-age=0, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/site/" },
        ],
      },
    ];
  },
};

export default nextConfig;
