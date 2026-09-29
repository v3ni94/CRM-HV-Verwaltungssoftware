import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const base = readFileSync(join(__dirname, "base.css"), "utf8");
const tokens = readFileSync(join(__dirname, "tokens.css"), "utf8");

function rule(css: string, selector: string): string {
  const start = css.indexOf(`\n${selector} {`);
  expect(start, `rule ${selector}`).toBeGreaterThanOrEqual(0);
  return css.slice(start, css.indexOf("}", start));
}

/** Review after M31 WP1: a sticky head with a non zero inset inside an `overflow-x: auto`
 *  wrapper is shifted over the first rows even at scroll position 0 (measured 64 px in
 *  Chromium). The default stays `top: 0`; the header offset is an opt in for tables that
 *  scroll with the page, and the shared token is 0 because the portal header is not sticky. */
describe("table head stickiness", () => {
  it("keeps top 0 for every mhvp-table head", () => {
    const head = rule(base, ".mhvp-table thead th");
    expect(head).toMatch(/position:\s*sticky/);
    expect(head).toMatch(/\btop:\s*0;/);
    expect(head).not.toContain("--mhvp-header-h");
  });

  it("offsets only the page variant by --mhvp-sticky-top", () => {
    const page = rule(base, ".mhvp-table--page thead th");
    expect(page).toMatch(/top:\s*var\(--mhvp-sticky-top, 0px\)/);
  });

  it("declares the shared offset as 0px so the portal is unaffected", () => {
    expect(tokens).toMatch(/--mhvp-sticky-top:\s*0px;/);
    expect(tokens).toMatch(/--mhvp-header-h:\s*3\.5rem;/);
    expect(tokens).toMatch(/--mhvp-header-h:\s*4rem;/);
    // the header height itself is never consumed by base.css rules
    expect(base).not.toMatch(/var\(--mhvp-header-h/);
  });
});
