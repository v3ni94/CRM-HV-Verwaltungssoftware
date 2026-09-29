import { screen, within } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { UnitDetails } from "./UnitDetails";

const unit = {
  id: "u1",
  property_id: "p",
  building_id: "b",
  number: "3",
  label: "WE 3",
  unit_type: "apartment",
  floor: "1. OG",
  location: "links",
  living_area_sqm: "72.30000000",
  custom_fields: { altsystem: { quelle: "Immoware24 Objektdaten", mieter: "Alt Mieter" }, stellplatz: "P4" },
  allocation_values: [
    { id: "v1", unit_id: "u1", allocation_key_id: "k1", key_code: "MEA", key_name: "Miteigentumsanteil", value: "125.00000000", valid_from: "2020-01-01", valid_to: null, source: "manual" },
    { id: "v2", unit_id: "u1", allocation_key_id: "k2", key_code: "WFL", key_name: "Wohnfläche", value: "72.30000000", valid_from: "2020-01-01", valid_to: null, source: "manual" },
  ],
};

const owner = {
  contract_id: "c1",
  contract_number: "000011",
  kind: "ownership",
  party_id: "p1",
  party_name: "Anna Eigen",
  start_date: "2020-01-01",
  end_date: null,
  members: [{ contact_id: "k1", display_name: "Anna Eigen", share_percent: "100.00000000" }],
};

describe("UnitDetails", () => {
  it("shows parameters, allocation keys, legacy notes, owner and no tenant", () => {
    renderIntl(<UnitDetails unit={unit as never} occupants={{ owner, tenant: null, history: [] } as never} />);
    const params = screen.getByTestId("unit-parameters");
    expect(params).toHaveTextContent("1. OG");
    expect(params).toHaveTextContent("72,3 m²");
    expect(params).toHaveTextContent("Miteigentumsanteile125");
    expect(screen.getByTestId("unit-allocation")).toHaveTextContent("Wohnfläche (WFL)");
    expect(screen.getByTestId("unit-legacy")).toHaveTextContent("Alt Mieter");
    expect(screen.getByTestId("unit-custom")).toHaveTextContent("P4");
    expect(within(screen.getByTestId("unit-owner")).getByRole("link", { name: "Anna Eigen" })).toHaveAttribute("href", "/kontakte/k1");
    expect(screen.getByTestId("unit-owner")).toHaveTextContent("seit 01.01.2020");
    expect(screen.getByTestId("unit-tenant")).toHaveTextContent("kein Mieter");
  });

  it("shows the tenant with rent and ended contracts in the history", () => {
    const tenant = { ...owner, contract_id: "c2", kind: "tenancy", party_name: "Mia Miete", members: [{ contact_id: "k2", display_name: "Mia Miete" }], rent_gross: "950.00" };
    const old = { ...owner, contract_id: "c0", party_name: "Otto Alt", members: [], end_date: "2019-12-31", start_date: "2010-01-01" };
    renderIntl(<UnitDetails unit={unit as never} occupants={{ owner, tenant, history: [old] } as never} />);
    expect(screen.getByTestId("unit-tenant")).toHaveTextContent("Mia Miete");
    expect(screen.getByTestId("unit-tenant")).toHaveTextContent("950,00 EUR");
    const history = screen.getByTestId("unit-history");
    expect(history).toHaveTextContent("Beendete Verträge (1)");
    expect(history).toHaveTextContent("Otto Alt");
    expect(history).toHaveTextContent("bis 31.12.2019");
  });

  it("stacks definition lists through KeyValueList without a bare two column grid (M31)", () => {
    const { container } = renderIntl(<UnitDetails unit={unit as never} occupants={{ owner, tenant: null, history: [] } as never} />);
    expect(screen.getByTestId("unit-parameters-list")).toHaveTextContent("1. OG");
    expect(screen.getByTestId("unit-custom-list")).toHaveTextContent("P4");
    expect(screen.getByTestId("unit-legacy-list")).toHaveTextContent("Alt Mieter");
    for (const dl of Array.from(container.querySelectorAll("dl"))) {
      expect(dl.className).not.toMatch(/(^|\s)grid-cols-2(\s|$)/);
    }
  });
});
