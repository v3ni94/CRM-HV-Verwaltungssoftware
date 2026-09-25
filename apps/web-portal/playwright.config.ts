import { defineConfig, devices } from "@playwright/test";

const port = 3001;
// Local override for a pre-installed Chromium whose revision differs from the
// @playwright/test release. Only applied when the variable is set (never in CI,
// where the workflow installs matching browsers).
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;

// Tests tagged @backend need a running API with seeded data (scripts/e2e-backend.sh style
// setup; see apps/web-crm/scripts and apps/web-portal/e2e/auth.ts).
const withBackend = process.env.E2E_BACKEND === "1";

export default defineConfig({
  testDir: "./e2e",
  ...(withBackend ? {} : { grepInvert: /@backend/ }),
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  ...(withBackend ? { workers: 1 } : {}),
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(executablePath ? { launchOptions: { executablePath } } : {}),
      },
    },
  ],
  webServer: {
    // Requires a prior `pnpm build`.
    command: "pnpm start",
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      // Unreachable on purpose unless provided: the page must render without the API.
      MHVP_API_INTERNAL_URL: process.env.MHVP_API_INTERNAL_URL ?? "http://127.0.0.1:9",
    },
  },
});
