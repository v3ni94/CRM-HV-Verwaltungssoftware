import { defineConfig, devices } from "@playwright/test";

// Default 3001; E2E_PORT lets a parallel run use a free port (scripts/e2e-backend.sh).
const port = Number(process.env.E2E_PORT ?? 3001);
// Local override for a pre-installed Chromium whose revision differs from the
// @playwright/test release. Only applied when the variable is set (never in CI,
// where the workflow installs matching browsers).
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;

// Tests tagged @backend need a running API with seeded data (scripts/e2e-backend.sh style
// setup; see apps/web-crm/scripts and apps/web-portal/e2e/auth.ts).
const withBackend = process.env.E2E_BACKEND === "1";

// Shared launch options of every project (only the local Chromium override so far).
const launch = executablePath ? { launchOptions: { executablePath } } : {};

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
      // Desktop with a mouse: every spec except the @mobile ones.
      name: "chromium",
      grepInvert: /@mobile/,
      use: {
        ...devices["Desktop Chrome"],
        ...launch,
      },
    },
    // Phone and tablet projects (M31 WP4) run only the specs tagged @mobile, so the existing
    // @backend specs are not repeated per viewport. isMobile and hasTouch make Chromium report
    // a coarse pointer, which the 44 px targets of lib/ui.ts depend on (pointer-coarse).
    // iPhone and iPad presets are left out on purpose: CI has no WebKit; Safari and iPadOS are
    // checked by hand (docs/acceptance/M31-geraetepruefung.md).
    {
      name: "phone",
      grep: /@mobile/,
      use: {
        ...devices["Pixel 7"],
        viewport: { width: 390, height: 844 },
        ...launch,
      },
    },
    {
      name: "tablet",
      grep: /@mobile/,
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 820, height: 1180 },
        deviceScaleFactor: 2,
        isMobile: true,
        hasTouch: true,
        ...launch,
      },
    },
    {
      name: "tablet-landscape",
      grep: /@mobile/,
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1024, height: 768 },
        deviceScaleFactor: 2,
        isMobile: true,
        hasTouch: true,
        ...launch,
      },
    },
  ],
  webServer: {
    // Requires a prior `pnpm build` (NEXT_DIST_DIR selects the build folder, see next.config.ts).
    command: `pnpm exec next start --port ${port}`,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      // Unreachable on purpose unless provided: the page must render without the API.
      MHVP_API_INTERNAL_URL: process.env.MHVP_API_INTERNAL_URL ?? "http://127.0.0.1:9",
    },
  },
});
