/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverComponentsExternalPackages: [
      '@neo4j-labs/agent-memory',
      '@neo4j-labs/nams-ai-provider',
    ],
  },
};

module.exports = nextConfig;
