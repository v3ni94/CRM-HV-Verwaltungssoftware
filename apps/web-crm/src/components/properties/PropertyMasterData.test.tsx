import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { area, nonNegative, PropertyMasterData } from "./PropertyMasterData";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

describe("PropertyMasterData helpers", () => {
  it("nonNegative flags only negative numbers, accepts comma decimals and empty input", () => {
    const check = nonNegative("negativ");
    expect(check("-1")).toBe("negativ");
    expect(check("-0,5")).toBe("negativ");
    expect(check("0")).toBeNull();
    expect(check("12,5")).toBeNull();
    expect(check("")).toBeNull();
    expect(check(null)).toBeNull();
  });

  it("area formats with two decimals and square metres, empty stays empty", () => {
    expect(area("420.00")).toBe("420,00 m²");
    expect(area(null)).toBe("");
    expect(area("")).toBe("");
  });
});

describe("PropertyMasterData", () => {
  it("renders the section read only without edit right", () => {
    renderIntl(<PropertyMasterData property={{ id: "p1", version: 1, name: "Rheinallee 12" }} canEdit={false} />);
    expect(screen.getByTestId("property-master-data")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
  });
});
