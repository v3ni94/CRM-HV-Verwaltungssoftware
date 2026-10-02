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
    // GAI-605: run with `pnpm vitest run --coverage` once @vitest/coverage-v8 is installed. The
    // threshold is set only after a measured baseline (open point AJ31), never guessed.
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/**/*.d.ts"],
      reporter: ["text-summary", "json-summary"],
    },
  },
});
