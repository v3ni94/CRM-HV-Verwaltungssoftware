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

/** GAM-715: twin of apps/web-crm/src/lib/ui.ts (ADR 0013). Surfaces differ on purpose; the
 *  interactive tokens must keep the same focus and target size rules. */
describe("portal ui twin rules (GAM-715)", () => {
  it.each(["input", "button", "primary", "secondary", "danger", "buttonSm", "tab", "tabActive"] as const)("%s shows a visible keyboard focus ring", (key) => {
    expect(ui[key]).toContain("focus-visible:ring-2");
    expect(ui[key]).toContain("focus-visible:ring-focus");
  });
  it("input uses the same focus border colour as the CRM", () => {
    expect(ui.input).toContain("focus:border-accent-strong");
    expect(ui.input).toContain("sm:pointer-fine:min-h-10");
  });
});
