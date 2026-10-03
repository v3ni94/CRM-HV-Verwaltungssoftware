import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

/** AP24 (GAM-709, GAM-712): source scans for date formats and keyboard focus. */
function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}
const FILES = sources(join(__dirname, ".."));

describe("date formats (GAM-709)", () => {
  it("formats dates and timestamps only through lib/format.ts", () => {
    const offenders: string[] = [];
    for (const file of FILES) {
      readFileSync(file, "utf8")
        .split("\n")
        .forEach((line, index) => {
          if (/toLocale(Date|Time)String\(/.test(line) || /new Date\([^)]*\)\.toLocaleString\(/.test(line)) offenders.push(`${file}:${index + 1}`);
        });
    }
    expect(offenders).toEqual([]);
  });
});

describe("keyboard focus (GAM-712)", () => {
  it("pairs every focus:outline-none with a focus-visible ring", () => {
    const offenders: string[] = [];
    for (const file of FILES) {
      readFileSync(file, "utf8")
        .split("\n")
        .forEach((line, index) => {
          if (line.includes("focus:outline-none") && !line.includes("focus-visible:ring") && !line.includes("focusRing")) offenders.push(`${file}:${index + 1}`);
        });
    }
    expect(offenders).toEqual([]);
  });
  it("does not show a mouse click ring (focus:ring) next to outline-none", () => {
    const offenders = FILES.filter((file) => /focus:outline-none[^\n]*\sfocus:ring-2/.test(readFileSync(file, "utf8")));
    expect(offenders).toEqual([]);
  });
});
