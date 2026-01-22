/** @type {import('next').NextConfig} */
const nextConfig = {
  // Production optimizations
  reactStrictMode: true,
  swcMinify: true,
  compress: true,
  
  // Environment variables
  env: {
    CORE_API_URL: process.env.CORE_API_URL || process.env.NEXT_PUBLIC_CORE_API_URL || 'http://localhost:8000',
  },
  
  // Public environment variables (available in browser)
  publicRuntimeConfig: {
    CORE_API_URL: process.env.NEXT_PUBLIC_CORE_API_URL || 'http://localhost:8000',
    WS_URL: process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000',
  },
  
  // API rewrites for development (not needed in production as we use direct API calls)
  async rewrites() {
    if (process.env.NODE_ENV === 'development') {
      return [
        {
          source: '/api/proxy/:path*',
          destination: `${process.env.CORE_API_URL || process.env.NEXT_PUBLIC_CORE_API_URL || 'http://localhost:8000'}/v1/:path*`,
        },
      ]
    }
    return []
  },
  
  // Security headers
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'X-DNS-Prefetch-Control',
            value: 'on'
          },
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=63072000; includeSubDomains; preload'
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff'
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY'
          },
          {
            key: 'X-XSS-Protection',
            value: '1; mode=block'
          },
          {
            key: 'Referrer-Policy',
            value: 'origin-when-cross-origin'
          }
        ],
      },
    ]
  },
}

module.exports = nextConfig

