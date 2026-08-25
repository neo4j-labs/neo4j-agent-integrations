/** @type {import('next').NextConfig} */

// Next 15.2+ blocks cross-origin requests to its dev-only `/_next/*` resources
// unless the requesting host is allowlisted. Only `localhost` and `**.localhost`
// are allowed by default, so reaching the dev server any other way — over
// 127.0.0.1, an IPv6 loopback, or a forwarded Codespaces URL — loads the page
// but fails to hydrate. This affects `next dev` only; production builds ignore it.
//
// Set NEXT_ALLOWED_DEV_ORIGINS (comma-separated) to add more hosts, e.g. a LAN
// IP or another remote devcontainer domain.
const extraDevOrigins = (process.env.NEXT_ALLOWED_DEV_ORIGINS ?? '')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean);

const nextConfig = {
  allowedDevOrigins: [
    'localhost',
    '127.0.0.1',
    '[::1]',
    '**.app.github.dev',
    ...extraDevOrigins,
  ],

  serverExternalPackages: [
    '@neo4j-labs/agent-memory',
    '@neo4j-labs/nams-ai-provider',
  ],
};

module.exports = nextConfig;
