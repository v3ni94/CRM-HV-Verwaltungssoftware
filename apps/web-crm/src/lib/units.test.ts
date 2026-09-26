// @vitest-environment node
import { formatQty, naturalCompare, occupantName, sortUnits, unitNumberFormatter } from "./units";

describe("naturalCompare", () => {
  it("orders numbers numerically", () => {
    expect(["10", "2", "1", "11", "3"].sort(naturalCompare)).toEqual(["1", "2", "3", "10", "11"]);
  });
  it("orders prefixed numbers numerically within the prefix", () => {
    expect(["WE10", "WE2", "WE1", "GE1", "TG3"].sort(naturalCompare)).toEqual(["GE1", "TG3", "WE1", "WE2", "WE10"]);
  });
  it("puts pure numbers before text and keeps zero padded values stable", () => {
    expect(["WE1", "2", "001", "1"].sort(naturalCompare)).toEqual(["001", "1", "2", "WE1"]);
  });
  it("sorts unit objects without changing them", () => {
    const units = [{ number: "10" }, { number: "1" }];
    expect(sortUnits(units).map((u) => u.number)).toEqual(["1", "10"]);
    expect(units[0]?.number).toBe("10");
  });
});

describe("unitNumberFormatter", () => {
  it("pads to three digits when all numbers are numeric", () => {
    const f = unitNumberFormatter(["1", "10", "2"]);
    expect(["1", "10", "2"].map(f)).toEqual(["001", "010", "002"]);
  });
  it("keeps numbers as stored when one is not numeric", () => {
    const f = unitNumberFormatter(["1", "WE2"]);
    expect(f("1")).toBe("1");
  });
});

describe("formatQty and occupantName", () => {
  it("formats quantities without float", () => {
    expect(formatQty("65.50000000")).toBe("65,5");
    expect(formatQty("1234.00000000")).toBe("1.234");
    expect(formatQty(null)).toBe("");
  });
  it("prefers member names", () => {
    expect(occupantName({ party_name: "P", members: [{ display_name: "Anna Muster" }, { display_name: "Ben Muster" }] })).toBe("Anna Muster, Ben Muster");
    expect(occupantName({ party_name: "Erbengemeinschaft", members: [] })).toBe("Erbengemeinschaft");
  });
});
