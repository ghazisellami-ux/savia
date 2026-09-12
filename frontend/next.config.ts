import type { NextConfig } from "next";

const isProduction = process.env.NODE_ENV === 'production';
const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "frame-src 'none'",
  "img-src 'self' blob: data: https://*.tile.openstreetmap.org https://*.basemaps.cartocdn.com https://services.arcgisonline.com",
  "font-src 'self' data:",
  "style-src 'self' 'unsafe-inline' https://unpkg.com",
  `script-src 'self' 'unsafe-inline'${isProduction ? '' : " 'unsafe-eval'"} https://unpkg.com`,
  "connect-src 'self' https://api.telegram.org",
  "worker-src 'self' blob:",
  "manifest-src 'self'",
  "media-src 'self'",
].join('; ');

const nextConfig: NextConfig = {
  output: 'standalone',
  experimental: {
    // Documents techniques are sent as JSON/base64 through the rewrite below.
    // A 20 MiB file therefore occupies about 26.7 MiB in transit.  Keep the
    // proxy allowance just above that transport size; the Python API remains
    // the authority that enforces the real 20 MiB file limit.
    proxyClientMaxBodySize: '28mb',
  },
  // Proxy API requests to the Python backend
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/api/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          ...(process.env.NODE_ENV === 'production'
            ? [{ key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' }]
            : []),
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Referrer-Policy', value: 'same-origin' },
          { key: 'Permissions-Policy', value: 'camera=(self), geolocation=(), microphone=()' },
          { key: 'Content-Security-Policy', value: contentSecurityPolicy },
          { key: 'Cross-Origin-Opener-Policy', value: 'same-origin' },
          { key: 'Cross-Origin-Resource-Policy', value: 'same-origin' },
        ],
      },
    ];
  },
};

export default nextConfig;
