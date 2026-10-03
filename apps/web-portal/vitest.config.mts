import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import { discoverLocales } from "./src/lib/locale-files";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  test: {
    env: { NEXT_PUBLIC_PORTAL_LOCALES: discoverLocales(path.resolve(import.meta.dirname, "messages")).join(",") },
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // GAI-619: explicit limits (default 5000 ms is too tight under 20 parallel runs, too loose to
    // hide hangs); override per test with it(name, fn, ms) only with a reason.
    testTimeout: 15_000,
    hookTimeout: 15_000,
    // GAI-605: `pnpm vitest run --coverage`. Baseline 03.10.2026 (AK15): statements 75,8 %,
    // branches 68,0 %, functions 80,2 %, lines 77,7 %. Thresholds sit just below the baseline.
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/**/*.d.ts"],
      reporter: ["text-summary", "json-summary"],
      thresholds: { statements: 74, branches: 66, functions: 78, lines: 76 },
    },
  },
});
