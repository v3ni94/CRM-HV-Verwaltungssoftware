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

  it("buttonSm grows to 44 px on coarse pointers", () => {
    expect(ui.buttonSm).toContain("pointer-coarse:min-h-11");
    expect(ui.buttonSm).toContain("pointer-coarse:px-3");
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
