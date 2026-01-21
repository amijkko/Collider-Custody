/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverActions: {
      allowedOrigins: ['localhost:3000'],
    },
  },
  env: {
    CORE_API_URL: process.env.CORE_API_URL || 'http://localhost:8000',
  },
  async rewrites() {
    return [
      // Proxy API requests to Core API in development
      {
        source: '/api/proxy/:path*',
        destination: `${process.env.CORE_API_URL || 'http://localhost:8000'}/v1/:path*`,
      },
    ]
  },
}

module.exports = nextConfig

