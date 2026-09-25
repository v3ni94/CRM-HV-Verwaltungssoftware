import { formatDate, formatEur, parseGermanDecimal } from "./format";

describe("formatEur", () => {
  it("formats decimal strings in German notation", () => {
    expect(formatEur("1234.5")).toBe("1.234,50 EUR");
    expect(formatEur("0")).toBe("0,00 EUR");
    expect(formatEur("-987654.321")).toBe("-987.654,32 EUR");
    expect(formatEur(null)).toBe("");
  });
});

describe("formatDate", () => {
  it("renders plain dates as TT.MM.JJJJ", () => {
    expect(formatDate("2026-09-25")).toBe("25.09.2026");
    expect(formatDate(null)).toBe("");
  });
});

describe("parseGermanDecimal", () => {
  it("converts German input to an API decimal string", () => {
    expect(parseGermanDecimal("1.250,50")).toBe("1250.50");
    expect(parseGermanDecimal("1234,5")).toBe("1234.5");
    expect(parseGermanDecimal("42")).toBe("42");
    expect(parseGermanDecimal("abc")).toBeNull();
    expect(parseGermanDecimal("")).toBeNull();
  });
});
