import { screen, within } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { UnitsTable } from "./UnitsTable";

const base = { building_id: "b", property_id: "p", unit_type: "apartment" as const, custom_fields: {}, allocation_values: [] };
const occupant = (name: string) => ({
  contract_id: `c-${name}`,
  contract_number: "000001",
  kind: "ownership",
  party_id: `p-${name}`,
  party_name: name,
  start_date: "2020-01-01",
  end_date: null,
  members: [{ contact_id: `k-${name}`, display_name: name }],
});

describe("UnitsTable", () => {
  it("sorts naturally, pads numeric numbers and links number and label", () => {
    renderIntl(
      <UnitsTable
        units={[
          { ...base, id: "u10", number: "10", label: "Dachgeschoss", living_area_sqm: "65.50000000" },
          { ...base, id: "u2", number: "2", label: null },
          { ...base, id: "u1", number: "1", label: "EG links", owner: occupant("Anna Eigen"), tenant: { ...occupant("Mia Miete"), kind: "tenancy" } },
        ] as never}
      />,
    );
    const rows = within(screen.getByTestId("units")).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[0]?.textContent)).toEqual(["001", "002", "010"]);
    expect(within(rows[0]!).getByRole("link", { name: "001" })).toHaveAttribute("href", "/vermietung/einheit/u1");
    expect(within(rows[0]!).getByRole("link", { name: "EG links" })).toHaveAttribute("href", "/vermietung/einheit/u1");
    expect(rows[0]).toHaveTextContent("Anna Eigen");
    expect(rows[0]).toHaveTextContent("Mia Miete");
    expect(rows[1]).toHaveTextContent("kein Mieter");
    expect(rows[2]).toHaveTextContent("65,5 m²");
  });

  it("keeps numbers as stored when they are not all numeric", () => {
    renderIntl(<UnitsTable units={[{ ...base, id: "a", number: "WE10" }, { ...base, id: "b", number: "WE2" }, { ...base, id: "c", number: "1" }] as never} />);
    const rows = within(screen.getByTestId("units")).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[0]?.textContent)).toEqual(["1", "WE2", "WE10"]);
  });
});
