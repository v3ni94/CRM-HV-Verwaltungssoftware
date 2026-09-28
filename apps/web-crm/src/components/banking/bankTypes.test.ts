import { fromCents, parseAmount, toCents } from "./bankTypes";

describe("parseAmount", () => {
  it("reads the displayed German notation, the plain German and the API notation", () => {
    expect(parseAmount("1.250,00")).toBe("1250.00");
    expect(parseAmount("1250,00")).toBe("1250.00");
    expect(parseAmount("1250.00")).toBe("1250.00");
    expect(parseAmount("-12,5")).toBe("-12.50");
    expect(parseAmount("-79.90")).toBe("-79.90");
    expect(parseAmount(" 300,00 ")).toBe("300.00");
    expect(parseAmount("1.234.567,89")).toBe("1234567.89");
    expect(parseAmount("1,234.56")).toBe("1234.56");
    expect(parseAmount("1.250")).toBe("1250.00");
    expect(parseAmount("1.5")).toBe("1.50");
    expect(parseAmount("007")).toBe("7.00");
    expect(parseAmount("+5")).toBe("5.00");
    expect(parseAmount("0")).toBe("0.00");
    expect(parseAmount("-0,00")).toBe("0.00");
  });

  it("returns null for input it cannot read instead of guessing", () => {
    expect(parseAmount("")).toBeNull();
    expect(parseAmount("   ")).toBeNull();
    expect(parseAmount(null)).toBeNull();
    expect(parseAmount(undefined)).toBeNull();
    expect(parseAmount("abc")).toBeNull();
    expect(parseAmount("1.250.00")).toBeNull();
    expect(parseAmount("12,34,5")).toBeNull();
    expect(parseAmount("1,234")).toBeNull();
    expect(parseAmount("1.2345")).toBeNull();
    expect(parseAmount("12 EUR")).toBeNull();
    expect(parseAmount("--5")).toBeNull();
  });
});

describe("toCents and fromCents", () => {
  it("builds integer cents from the digit strings, never through a float", () => {
    expect(toCents("1.250,00")).toBe(125000);
    expect(toCents("1250.00")).toBe(125000);
    expect(toCents("-79.90")).toBe(-7990);
    expect(toCents("0.29")).toBe(29);
    expect(toCents("1.15")).toBe(115);
    expect(toCents("-12,5")).toBe(-1250);
    expect(toCents(12.5)).toBe(1250);
  });

  it("counts unreadable and empty input as 0", () => {
    expect(toCents("")).toBe(0);
    expect(toCents(null)).toBe(0);
    expect(toCents(undefined)).toBe(0);
    expect(toCents("abc")).toBe(0);
    expect(toCents("1.250.00")).toBe(0);
    expect(toCents(Number.NaN)).toBe(0);
  });

  it("round trips through fromCents", () => {
    expect(fromCents(125000)).toBe("1250.00");
    expect(fromCents(-7990)).toBe("-79.90");
    expect(fromCents(5)).toBe("0.05");
    expect(toCents(fromCents(-7990))).toBe(-7990);
  });
});
