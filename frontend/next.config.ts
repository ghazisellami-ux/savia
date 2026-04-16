import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'standalone',
  // Proxy API requests to the Python backend
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://backend:8000'}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
