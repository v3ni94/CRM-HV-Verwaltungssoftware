import { readFileSync } from "node:fs";
import path from "node:path";

import manifest from "./manifest";

/** The manifest cannot read CSS, so its colours are a hex copy of the day tokens; this guard
 *  fails when packages/ui/src/tokens.css moves on without the copy (M31 WP5). */
function dayToken(name: string): string {
  const css = readFileSync(path.resolve(import.meta.dirname, "../../../../packages/ui/src/tokens.css"), "utf8");
  const root = css.slice(css.indexOf(":root {"), css.indexOf(":root[data-theme"));
  const match = new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`).exec(root);
  if (!match) throw new Error(`token ${name} not found`);
  return match[1]!.toLowerCase();
}

describe("CRM manifest (M30-08)", () => {
  it("describes the installable shell with the day tokens and the icons of the brand mark", () => {
    const m = manifest();
    expect(m.name).toBe("MH Verwaltungsplattform");
    expect(m.short_name).toBe("MHVP");
    expect(m.id).toBe("/start");
    expect(m.start_url).toBe("/start");
    expect(m.display).toBe("standalone");
    expect(m.theme_color).toBe(dayToken("--mhvp-color-bg"));
    expect(m.background_color).toBe(dayToken("--mhvp-color-bg"));
    expect(m.icons?.map((i) => [i.src, i.purpose])).toEqual([
      ["/icons/icon-192.png", "any"],
      ["/icons/icon-512.png", "any"],
      ["/icons/icon-512-maskable.png", "maskable"],
    ]);
    expect(m.shortcuts?.map((s) => s.url)).toEqual(["/makler/uebergabe", "/kalender", "/tickets"]);
  });
});
