import { readFileSync } from "node:fs";
import { join } from "node:path";

import { ui } from "./ui";

/** Touch sizes follow the pointer, not the width (M31, plan WP1 step 2): every control keeps
 *  44 px and shrinks to 40 px only from `sm` with a fine pointer. A bare `sm:min-h-10` would
 *  shrink tablets again. */
const BARE_SM_MIN_H_10 = /(^|\s)sm:min-h-10(\s|$)/;

describe("ui class sets (M31)", () => {
  it.each(["input", "button", "primary", "secondary", "danger"] as const)("%s keeps 44 px and shrinks only with a fine pointer", (key) => {
    expect(ui[key]).toContain("min-h-11");
    expect(ui[key]).not.toMatch(BARE_SM_MIN_H_10);
    expect(ui[key]).toContain("sm:pointer-fine:min-h-10");
  });

  it("buttonSm keeps 44 px and shrinks to 36 px only with a fine pointer (GAJ-403)", () => {
    expect(ui.buttonSm).toContain("min-h-11");
    expect(ui.buttonSm).not.toMatch(/(^|\s)min-h-9(\s|$)/);
    expect(ui.buttonSm).toContain("pointer-fine:min-h-9");
  });

  it("every interactive token is 44 px on coarse pointers (GAJ-403)", () => {
    const interactive = ["input", "button", "primary", "secondary", "danger", "buttonSm", "tab", "tabActive", "segment", "segmentActive"] as const;
    for (const key of interactive) {
      expect(ui[key], key).toMatch(/(^|\s)min-h-11(\s|$)/);
      expect(ui[key], key).not.toMatch(/(^|\s)min-h-(?:[0-9]|10)(\s|$)/);
    }
    expect(ui.iconButton).toMatch(/(^|\s)h-11(\s|$)/);
    expect(ui.iconButton).toMatch(/(^|\s)w-11(\s|$)/);
  });

  it("input uses 16 px text on phones against the iOS focus zoom", () => {
    expect(ui.input).toContain("text-base");
    expect(ui.input).toContain("sm:text-sm");
  });

  it("bottomBar honours the safe area and keeps the AI launcher corner free", () => {
    expect(ui.bottomBar).toContain("env(safe-area-inset-bottom)");
    expect(ui.bottomBar).toContain("pr-20");
    expect(ui.bottomBar).toContain("sticky bottom-0");
  });

  it("tabs are 44 px high and the bar scrolls horizontally", () => {
    expect(ui.tab).toContain("min-h-11");
    expect(ui.tabActive).toContain("min-h-11");
    expect(ui.tabActive).toContain("bg-accent-soft");
    expect(ui.tabBar).toContain("overflow-x-auto");
    expect(ui.tabBar).toContain("snap-x");
  });

  it("table wrappers scroll instead of overflowing the page", () => {
    expect(ui.tableScroll).toContain("overflow-x-auto");
    expect(ui.tableCard).toContain("overflow-x-auto");
    expect(ui.tableCard).toContain("p-0");
    expect(ui.tableCard).not.toContain("p-4");
    expect(ui.cardsMobile).toContain("sm:hidden");
  });

  it("keeps table heads at top 0 and offsets only the page table below the header (review WP1)", () => {
    expect(ui.table).toBe("mhvp-table");
    expect(ui.tablePage).toBe("mhvp-table mhvp-table--page");
    expect(ui.tableCard).not.toContain("mhvp-table--page");
    expect(ui.tableScroll).not.toContain("mhvp-table--page");
    const globals = readFileSync(join(__dirname, "../app/globals.css"), "utf8");
    expect(globals).toMatch(/--mhvp-sticky-top:\s*var\(--mhvp-header-h\);/);
  });

  it("segments and icon buttons follow the pointer", () => {
    expect(ui.segment).toContain("min-h-11");
    expect(ui.segmentActive).toContain("min-h-11");
    expect(ui.iconButton).toContain("h-11 w-11");
    expect(ui.iconButton).toContain("sm:pointer-fine:h-9");
    expect(ui.iconButton).toContain("sm:pointer-fine:w-9");
  });

  it("uses only the built in pointer variants, never a custom one", () => {
    for (const value of Object.values(ui)) {
      expect(value).not.toMatch(/(^|\s)(coarse|fine|touch|mouse):/);
    }
  });
});
