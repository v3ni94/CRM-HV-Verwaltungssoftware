import { describe, expect, it } from "vitest";

import { formatPercent } from "./AvailabilityAdmin";

describe("formatPercent (GB16-02)", () => {
  it("shows three places with the German decimal comma", () => {
    expect(formatPercent("99.69761905")).toBe("99,698 %");
    expect(formatPercent("99.5")).toBe("99,500 %");
  });
  it("shows a dash without a figure", () => {
    expect(formatPercent(null)).toBe("-");
  });
});
