import { describe, expect, it } from "vitest";

import { formatCoverage } from "./AvailabilitySelfMeasurement";

describe("formatCoverage (AE35)", () => {
  it("shows one place with the German decimal comma", () => {
    expect(formatCoverage("100.000")).toBe("100,0 %");
    expect(formatCoverage("23.148")).toBe("23,1 %");
  });
  it("shows a dash without a figure", () => {
    expect(formatCoverage(null)).toBe("-");
  });
});
