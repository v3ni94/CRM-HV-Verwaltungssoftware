import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // GAI-619: explicit limits (default 5000 ms is too tight under 20 parallel runs, too loose to
    // hide hangs); override per test with it(name, fn, ms) only with a reason.
    testTimeout: 15_000,
    hookTimeout: 15_000,
    // GAI-605: `pnpm vitest run --coverage`. Baseline 03.10.2026 (AK15): statements 73,2 %,
    // branches 64,8 %, functions 69,9 %, lines 75,0 %. Thresholds sit just below the baseline.
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/**/*.d.ts"],
      reporter: ["text-summary", "json-summary"],
      thresholds: { statements: 71, branches: 62, functions: 67, lines: 73 },
    },
  },
});
