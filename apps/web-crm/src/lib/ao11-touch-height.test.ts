import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

/** AO11 (AN13): a control built on ui.input must not override its 44 px touch height with a bare
 *  min-h-9; the shrink to 36 px is allowed only behind the pointer-fine variant. */
function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.tsx$/.test(name) && !/\.test\.tsx$/.test(name) ? [path] : [];
  });
}

describe("touch height of ui.input fields (AN13)", () => {
  it("has no bare min-h-9 next to ui.input", () => {
    const offenders: string[] = [];
    for (const file of sources(join(__dirname, ".."))) {
      readFileSync(file, "utf8")
        .split("\n")
        .forEach((line, index) => {
          if (line.includes("ui.input") && /(^|[\s"`])min-h-9(\s|$|[`"])/.test(line)) {
            offenders.push(`${file}:${index + 1}`);
          }
        });
    }
    expect(offenders).toEqual([]);
  });

  it.each(["components/workspace/TicketThroughput.tsx", "components/dashboard/TicketAnalytics.tsx"])(
    "%s keeps the filter fields at pointer-fine:min-h-9",
    (rel) => {
      const text = readFileSync(join(__dirname, "..", rel), "utf8");
      expect(text).toContain("pointer-fine:min-h-9");
    },
  );
});
