import { filterQuery } from "./audit-filter";

describe("filterQuery", () => {
  it("keeps only known keys, trims and drops empty values", () => {
    expect(filterQuery({})).toBe("");
    expect(filterQuery({ account_id: " a1 ", q: "", date_from: "2025-01-01", foo: "x" } as never)).toBe(
      "?account_id=a1&date_from=2025-01-01",
    );
    expect(filterQuery({ vendor_contact_id: ["v1", "v2"] })).toBe("?vendor_contact_id=v1");
  });
});
