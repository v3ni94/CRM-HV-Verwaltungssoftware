import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

/** Source guard (M31 WP4, twin of apps/web-crm/src/lib/no-fixed-width.test.ts): no `.tsx`/`.ts`
 *  file under `src/` may hard code a pixel width above 360px in a className (for example
 *  `w-[420px]`, `min-w-[500px]`), since that overflows a 375px phone viewport. Widths at or
 *  below 360px and non-pixel units (rem, vw, %, ch) are allowed. No excluded areas. */

const ROOT = path.resolve(import.meta.dirname, "..");

function listFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...listFiles(full));
    else if (/\.(tsx?|jsx?)$/.test(entry) && !entry.endsWith(".test.ts") && !entry.endsWith(".test.tsx")) out.push(full);
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
        if (Number(match[1]) > 360) offenders.push(`${path.relative(ROOT, file)}: ${match[0]}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
