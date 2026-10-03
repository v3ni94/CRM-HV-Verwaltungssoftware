import { describe, expect, it } from "vitest";

import { formatEur } from "./format";
import { centsToDecimal, sumCents } from "./money";

// GAM-710: sums of money in integer cents, never through a binary float.
describe("money sums (GAM-710)", () => {
  it("adds decimal strings exactly", () => {
    expect(centsToDecimal(sumCents(["0.10", "0.20"]) ?? 0n)).toBe("0.30");
    expect(formatEur(centsToDecimal(sumCents(["0.10", "0.20"]) ?? 0n))).toBe("0,30 EUR");
  });

  it("keeps large amounts exact", () => {
    const total = sumCents(["90071992547409.91", "0.01"]) ?? 0n;
    expect(centsToDecimal(total)).toBe("90071992547409.92");
  });

  it("formats with a comma, never a point", () => {
    expect(formatEur("1234.5")).toBe("1.234,50 EUR");
    expect(formatEur(centsToDecimal(sumCents(["-1.005"]) ?? 0n))).toBe("-1,01 EUR");
  });
});
