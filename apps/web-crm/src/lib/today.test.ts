import { describe, expect, it } from "vitest";
import { today } from "./today";

describe("today", () => {
  it("uses the Berlin day in summer after 22:00 UTC", () => {
    expect(today(new Date("2026-06-30T22:30:00Z"))).toBe("2026-07-01");
    expect(today(new Date("2026-06-30T21:59:00Z"))).toBe("2026-06-30");
  });
  it("uses the Berlin day in winter after 23:00 UTC", () => {
    expect(today(new Date("2026-12-31T23:30:00Z"))).toBe("2027-01-01");
    expect(today(new Date("2026-12-31T22:59:00Z"))).toBe("2026-12-31");
  });
});

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\./.test(name)) out.push(p);
  }
  return out;
}

describe("no UTC day for form defaults", () => {
  it("does not use new Date().toISOString().slice(0, 10)", () => {
    const bad = walk(join(__dirname, "..")).filter((f) =>
      /new Date\(\)\.toISOString\(\)\.slice\(0, ?10\)/.test(readFileSync(f, "utf8")),
    );
    expect(bad).toEqual([]);
  });
});
