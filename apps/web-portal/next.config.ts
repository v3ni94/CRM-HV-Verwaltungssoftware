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
};

export default withNextIntl(nextConfig);
