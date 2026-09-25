import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

/** Regression check for the mobile visual audit (operator feedback item 4): no `.tsx`/`.ts`
 *  source file under `src/` may hard code a pixel width above 360px in a className string
 *  (e.g. `w-[420px]`, `min-w-[500px]`), since that reliably causes horizontal overflow on a
 *  375px phone viewport. Widths at or below 360px, and any non-pixel unit (rem, vw, %, ch),
 *  are allowed. `bank`, `tickets` and `kalender` areas are excluded: they are owned by other
 *  agents in this workstream and audited separately. */

const ROOT = path.resolve(import.meta.dirname, "..");
const EXCLUDED_DIRS = [
  path.join(ROOT, "app", "(app)", "start"),
  path.join(ROOT, "app", "(app)", "tickets"),
  path.join(ROOT, "app", "(app)", "bank"),
  path.join(ROOT, "app", "(app)", "kalender"),
  path.join(ROOT, "components", "tickets"),
  path.join(ROOT, "components", "banking"),
];

function listFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      if (EXCLUDED_DIRS.includes(full)) continue;
      out.push(...listFiles(full));
    } else if (/\.(tsx?|jsx?)$/.test(entry) && !entry.endsWith(".test.ts") && !entry.endsWith(".test.tsx")) {
      out.push(full);
    }
  }
  return out;
}

const PX_WIDTH = /\b(?:w|min-w|max-w)-\[(\d+)px\]/g;

describe("no fixed pixel widths above 360px", () => {
  it("keeps every className free of a hard coded width that overflows a 375px phone", () => {
    const offenders: string[] = [];
    for (const file of listFiles(ROOT)) {
      const content = readFileSync(file, "utf8");
      for (const match of content.matchAll(PX_WIDTH)) {
        const value = Number(match[1]);
        if (value > 360) {
          offenders.push(`${path.relative(ROOT, file)}: ${match[0]}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
