import { ui } from "./ui";

/** Touch targets (GAJ-403, M31): every interactive token is 44 px high on any device with a
 *  coarse pointer and shrinks only with a fine pointer. A bare `min-h-9` or `sm:min-h-10`
 *  would shrink phones and tablets again. */
const INTERACTIVE = ["input", "button", "primary", "secondary", "danger", "buttonSm", "tab", "tabActive"] as const;
const BARE_SMALL = /(^|\s)(?:sm:)?min-h-(?:[0-9]|10)(\s|$)/;

describe("portal ui class sets (GAJ-403)", () => {
  it.each(INTERACTIVE)("%s is 44 px and shrinks only with a fine pointer", (key) => {
    expect(ui[key]).toMatch(/(^|\s)min-h-11(\s|$)/);
    expect(ui[key]).not.toMatch(BARE_SMALL);
  });

  it("buttonSm shrinks to 36 px only with a fine pointer", () => {
    expect(ui.buttonSm).toContain("pointer-fine:min-h-9");
  });

  it("inputs keep 16 px text below sm", () => {
    expect(ui.input).toContain("text-base");
    expect(ui.input).toContain("sm:text-sm");
  });
});
