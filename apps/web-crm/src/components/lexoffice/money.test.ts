import { formatCents, localTotals, parseDecimal } from "./money";

describe("lexoffice money helpers", () => {
  it("parses German and plain decimal strings without float", () => {
    expect(parseDecimal("1.234,56")).toBe("1234.56");
    expect(parseDecimal("1234,5")).toBe("1234.5");
    expect(parseDecimal("1234.56")).toBe("1234.56");
    expect(parseDecimal("12")).toBe("12");
    expect(parseDecimal("")).toBeNull();
    expect(parseDecimal("abc")).toBeNull();
    expect(parseDecimal("1,23456")).toBeNull();
  });

  it("computes net control sums like payloads.invoice_totals (half up to cents)", () => {
    expect(localTotals("net", [{ quantity: "2", unit_price: "100", tax_rate_percent: 19 }])).toEqual({
      net: "200,00 EUR",
      tax: "38,00 EUR",
      gross: "238,00 EUR",
    });
    expect(localTotals("net", [{ quantity: "1", unit_price: "0.005", tax_rate_percent: 0 }])).toEqual({
      net: "0,01 EUR",
      tax: "0,00 EUR",
      gross: "0,01 EUR",
    });
  });

  it("computes gross sums by dividing out the tax", () => {
    expect(localTotals("gross", [{ quantity: "1", unit_price: "119", tax_rate_percent: 19 }])).toEqual({
      net: "100,00 EUR",
      tax: "19,00 EUR",
      gross: "119,00 EUR",
    });
  });

  it("formats thousands and negatives", () => {
    expect(formatCents(123456789n)).toBe("1.234.567,89 EUR");
    expect(formatCents(-5n)).toBe("-0,05 EUR");
  });
});
