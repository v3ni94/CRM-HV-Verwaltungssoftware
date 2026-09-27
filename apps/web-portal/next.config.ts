import path from "node:path";
import { fileURLToPath } from "node:url";

import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  output: "standalone",
  // Test runs may build into their own folder (e.g. .next-e2e) so parallel builds do not collide.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  outputFileTracingRoot: repoRoot,
  transpilePackages: ["@mhvp/ui", "@mhvp/api-client"],
  poweredByHeader: false,
  reactStrictMode: true,
  // Defence in depth (M27-02, Masterprompt Kapitel 16): Traefik already sets frameDeny,
  // contentTypeNosniff, referrerPolicy and HSTS at the edge (infra/traefik, compose.prod.yaml);
  // these headers repeat on every response in case the app is reached directly.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=()",
          },
          {
            key: "Content-Security-Policy",
            value:
              "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
          },
        ],
      },
    ];
  },
};

export default withNextIntl(nextConfig);
