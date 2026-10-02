import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// GAI-619: no test may be switched off or narrowed to one case without being noticed.
const ROOT = path.resolve(import.meta.dirname, "..", "..");
const PATTERN = /\b(?:it|test|describe)\.(?:skip|only|todo)\b|\b(?:xit|xdescribe|fit|fdescribe)\(/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (name === "node_modules" || name === ".next") return [];
    return statSync(full).isDirectory() ? files(full) : /\.test\.tsx?$/.test(name) && name !== "no-skipped-tests.test.ts" ? [full] : [];
  });
}

describe("test hygiene", () => {
  it("has no skipped, focused or todo tests in src", () => {
    const hits = files(path.join(ROOT, "src")).filter((f) => PATTERN.test(readFileSync(f, "utf-8")));
    expect(hits.map((f) => path.relative(ROOT, f))).toEqual([]);
  });
});
