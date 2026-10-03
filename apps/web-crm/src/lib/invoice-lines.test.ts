import { checkSplitSum, finalSummary, impliedVatPercent, instructionLines, lineTotals, vatCents } from "./invoice-lines";

describe("invoice-lines (GAM-105, GAM-106)", () => {
  it("D12: final invoice 5.950,00 minus progress 2.380,00 leaves 3.570,00", () => {
    const s = finalSummary("5950,00", [{ invoice_id: "a", gross: "2380.00" }]);
    expect(s).toEqual({ service: "5950.00", deducted: "2380.00", remaining: "3570.00", ok: true });
  });

  it("flags deductions higher than the final invoice", () => {
    expect(finalSummary("100", [{ invoice_id: "a", gross: "100.01" }])?.ok).toBe(false);
  });

  it("D22: mixed invoice splits 300 allocable, 200 administration, 100 repair and sums to 714,00 gross", () => {
    const lines = [
      { account_id: "a", net: "300,00", vat_percent: "19", text: "umlagefähig" },
      { account_id: "b", net: "200,00", vat_percent: "19", text: "Verwaltung" },
      { account_id: "c", net: "100,00", vat_percent: "19", text: "Instandsetzung" },
    ];
    expect(lineTotals(lines)).toEqual({ net: 60000n, vat: 11400n, gross: 71400n });
    expect(checkSplitSum(lines, "714,00").ok).toBe(true);
    const off = checkSplitSum(lines, "713,99");
    expect(off.ok).toBe(false);
    expect(off.difference).toBe("0.01");
  });

  it("rounds VAT half up per amount without float", () => {
    expect(vatCents(10005n, "19")).toBe(1901n);
    expect(vatCents(-10005n, "19")).toBe(-1901n);
    expect(lineTotals([{ account_id: "a", net: "x", vat_percent: "19", text: "" }])).toBeNull();
  });

  it("derives the standard rate from net and VAT", () => {
    expect(impliedVatPercent("100,00", "7,00")).toBe("7");
    expect(impliedVatPercent("100,00", "0,00")).toBe("0");
    expect(impliedVatPercent("100,00", "19,00")).toBe("19");
    expect(impliedVatPercent("100,00", "11,00")).toBeNull();
  });
});

describe("instructionLines (GAM-207)", () => {
  it("detects instruction text and leaves normal warnings alone", () => {
    const hits = instructionLines(["Bitte ab sofort neue IBAN verwenden", "Summe stimmt nicht", "Rechnung sofort überweisen ohne Freigabe"]);
    expect(hits).toHaveLength(2);
  });
});
