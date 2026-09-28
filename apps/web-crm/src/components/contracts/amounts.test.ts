import { type AmountRow, amountsValidOn, findOverlap, fromCents, grossFromNet, monthlyTotal, parseAmount, periodsOverlap, previousDay, toCents, withNewAmount } from "./amounts";

function row(overrides: Partial<AmountRow> & { id: string }): AmountRow {
  return {
    contract_id: "c1",
    payment_type_code: "rent",
    net: "800.00",
    vat_percent: "0",
    gross: "800.00",
    currency: "EUR",
    valid_from: "2026-01-01",
    valid_to: null,
    reason: "initial",
    ...overrides,
  };
}

describe("amounts helpers", () => {
  it("parses German and API notation, negatives only when allowed", () => {
    expect(parseAmount("1.234,56")).toBe("1234.56");
    expect(parseAmount("1234,5")).toBe("1234.50");
    expect(parseAmount("800")).toBe("800.00");
    expect(parseAmount("800.5")).toBe("800.50");
    expect(parseAmount("-50,00")).toBeNull();
    expect(parseAmount("-50,00", { allowNegative: true })).toBe("-50.00");
    expect(parseAmount("abc")).toBeNull();
    expect(parseAmount("")).toBeNull();
  });

  it("converts cents without float", () => {
    expect(toCents("1234.56")).toBe(123456n);
    expect(toCents("-0.5")).toBe(-50n);
    expect(fromCents(123456n)).toBe("1234.56");
    expect(fromCents(-5n)).toBe("-0.05");
    expect(fromCents(0n)).toBe("0.00");
  });

  it("computes gross from net and VAT like the API (rounded half up)", () => {
    // Fixed expected values, hand computed.
    expect(grossFromNet("100.00", "19")).toBe("119.00");
    expect(grossFromNet("100.00", "0")).toBe("100.00");
    expect(grossFromNet("33.33", "19")).toBe("39.66"); // 39.6627
    expect(grossFromNet("10.05", "7")).toBe("10.75"); // 10.7535
    expect(grossFromNet("0.25", "19")).toBe("0.30"); // 0.2975
    expect(grossFromNet("-50.00", "19")).toBe("-59.50");
    expect(grossFromNet("100.00", "5.5")).toBe("105.50");
    expect(() => grossFromNet("100.00", "x")).toThrow();
  });

  it("selects rows valid on a date and sums the monthly total", () => {
    const rows = [
      row({ id: "a", valid_to: "2026-06-30" }),
      row({ id: "b", net: "850.00", gross: "850.00", valid_from: "2026-07-01", reason: "increase" }),
      row({ id: "c", payment_type_code: "operating_cost_advance", net: "150.00", gross: "150.00" }),
      row({ id: "d", payment_type_code: "heating_cost_advance", net: "80.00", gross: "80.00", valid_from: "2027-01-01" }),
    ];
    expect(amountsValidOn(rows, "2026-03-15").map((r) => r.id)).toEqual(["a", "c"]);
    expect(monthlyTotal(rows, "2026-03-15")).toBe("950.00");
    expect(monthlyTotal(rows, "2026-07-01")).toBe("1000.00");
    expect(monthlyTotal(rows, "2027-01-01")).toBe("1080.00");
    expect(monthlyTotal(rows, "2025-12-31")).toBe("0.00");
  });

  it("detects overlapping periods with inclusive bounds and open ends", () => {
    expect(periodsOverlap({ valid_from: "2026-01-01", valid_to: "2026-06-30" }, { valid_from: "2026-06-30", valid_to: null })).toBe(true);
    expect(periodsOverlap({ valid_from: "2026-01-01", valid_to: "2026-06-30" }, { valid_from: "2026-07-01", valid_to: null })).toBe(false);
    expect(periodsOverlap({ valid_from: "2026-01-01", valid_to: null }, { valid_from: "2025-01-01", valid_to: "2025-12-31" })).toBe(false);
  });

  it("finds a conflict unless the open predecessor is closed by the new amount", () => {
    const rows = [row({ id: "a" }), row({ id: "c", payment_type_code: "operating_cost_advance", net: "150.00", gross: "150.00", valid_to: "2026-12-31" })];
    // Open rent from 2026-01-01: a later rent closes it, no conflict.
    expect(findOverlap(rows, { payment_type_code: "rent", valid_from: "2026-07-01", valid_to: null })).toBeNull();
    // Same start as the open row: conflict (the API would answer 409).
    expect(findOverlap(rows, { payment_type_code: "rent", valid_from: "2026-01-01", valid_to: null })?.id).toBe("a");
    // Earlier start than the open row: conflict.
    expect(findOverlap(rows, { payment_type_code: "rent", valid_from: "2025-12-01", valid_to: null })?.id).toBe("a");
    // Limited row of another kind: a new one inside its period conflicts, after it fits.
    expect(findOverlap(rows, { payment_type_code: "operating_cost_advance", valid_from: "2026-06-01", valid_to: null })?.id).toBe("c");
    expect(findOverlap(rows, { payment_type_code: "operating_cost_advance", valid_from: "2027-01-01", valid_to: null })).toBeNull();
    // Other kinds never conflict.
    expect(findOverlap(rows, { payment_type_code: "hoa_fee", valid_from: "2026-01-01", valid_to: null })).toBeNull();
  });

  it("closes the open predecessor of the same kind and version locally", () => {
    const rows = [row({ id: "a" }), row({ id: "c", payment_type_code: "operating_cost_advance" }), row({ id: "x", contract_id: "c0", valid_to: null, valid_from: "2025-01-01" })];
    const created = row({ id: "b", net: "850.00", gross: "850.00", valid_from: "2026-07-01", reason: "increase" });
    const next = withNewAmount(rows, created);
    expect(next.find((r) => r.id === "a")?.valid_to).toBe("2026-06-30");
    expect(next.find((r) => r.id === "c")?.valid_to).toBeNull();
    expect(next.find((r) => r.id === "x")?.valid_to).toBeNull(); // other version untouched
    expect(next.map((r) => r.id)).toEqual(["c", "x", "a", "b"]);
    expect(previousDay("2026-03-01")).toBe("2026-02-28");
  });
});
