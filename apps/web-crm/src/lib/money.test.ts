import { describe, expect, it } from "vitest";

import { centsToDecimal, parseCents, settleAmount, sumCents, sumShares, warmRentDisplay } from "./money";

describe("money (integer cents)", () => {
  it("parses decimals without binary errors", () => {
    expect(parseCents("1.005")).toBe(101n); // plain decimal point, half up
    expect(parseCents("1,005")).toBe(101n);
    expect(parseCents("0.285")).toBe(29n);
    expect(parseCents("1.234,56")).toBe(123456n);
    expect(parseCents("1234.56")).toBe(123456n);
    expect(parseCents("-0,5")).toBe(-50n);
    expect(parseCents("-1.005")).toBe(-101n); // half up away from zero
    expect(parseCents(12.3)).toBe(1230n);
  });
  it("rejects invalid input", () => {
    for (const bad of ["", "abc", "1,2,3", "-", ".", null, undefined, Number.NaN]) {
      expect(parseCents(bad as string)).toBeNull();
    }
  });
  it("formats cents", () => {
    expect(centsToDecimal(-1230n)).toBe("-12.30");
    expect(centsToDecimal(5n)).toBe("0.05");
  });
  it("sums exactly", () => {
    expect(sumCents(["0.10", "0.20"])).toBe(30n);
    expect(sumCents(["0.10", "x"])).toBeNull();
  });
  it("computes the warm rent preview", () => {
    expect(warmRentDisplay("500.10", "100.20", "50.30", false)).toBe("650,60");
    expect(warmRentDisplay("500.10", "100.20", "50.30", true)).toBe("600,30");
    expect(warmRentDisplay("1.005", "", "", false)).toBe("1,01");
    expect(warmRentDisplay("abc", "", "", false)).toBeNull();
  });
  it("limits the settlement to the splits", () => {
    expect(settleAmount("-100.00", ["30.10", "20.20"])).toBe("50.30");
    expect(settleAmount("40.00", ["30.10", "20.20"])).toBe("40.00");
    expect(settleAmount("1.005", ["5.00"])).toBe("1.01");
  });
  it("sums percentage shares exactly", () => {
    expect(sumShares(["33,33333333", "66.66666667"])).toBe(100);
    expect(sumShares(["0.1", "0.2", null, ""])).toBeCloseTo(0.3, 10);
  });
});
