import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import type { ContractOut } from "./ContractForm";
import { ContractList, ContractSearch } from "./ContractList";

const row = (over: Partial<ContractOut>): ContractOut =>
  ({
    id: "c1",
    kind: "tenancy",
    number: "V-1",
    version: 1,
    property_id: "p1",
    unit_id: "u1",
    party_id: "pa1",
    legal_entity_id: "le1",
    start_date: "2026-01-01",
    end_date: null,
    approval_status: "approved",
    schedules: [],
    property_number: "336",
    property_name: "Gladbacher Straße 95",
    property_address: "Gladbacher Straße 95, 40219 Düsseldorf",
    unit_number: "01",
    unit_label: "WE 01",
    party_name: "Schmidt, Anna und Schmidt, Paul",
    members: [
      { contact_id: "k1", name: "Schmidt, Anna", role: "primary" },
      { contact_id: "k2", name: "Schmidt, Paul", role: "co_party" },
    ],
    ...over,
  }) as ContractOut;

describe("ContractList", () => {
  it("shows property, unit and persons with links", () => {
    renderIntl(<ContractList rows={[row({})]} />);
    expect(screen.getByRole("link", { name: "336 Gladbacher Straße 95" })).toHaveAttribute("href", "/objekte/p1");
    expect(screen.getByText("Gladbacher Straße 95, 40219 Düsseldorf")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "01 · WE 01" })).toHaveAttribute("href", "/vermietung/einheit/u1");
    expect(screen.getByRole("link", { name: "Schmidt, Anna" })).toHaveAttribute("href", "/kontakte/k1");
    expect(screen.getByRole("link", { name: "Schmidt, Paul" })).toHaveAttribute("href", "/kontakte/k2");
    expect(screen.getByRole("link", { name: "Öffnen" })).toHaveAttribute("href", "/vertraege/c1");
  });

  it("falls back to the party name without members", () => {
    renderIntl(<ContractList rows={[row({ kind: "ownership", members: [], party_name: "Erbengemeinschaft Weber" })]} />);
    expect(screen.getByText("Erbengemeinschaft Weber")).toBeInTheDocument();
  });
});

describe("ContractSearch", () => {
  it("renders a GET search form that keeps the filters", () => {
    const { container } = renderIntl(<ContractSearch q="Schmidt" hidden={{ property_id: "p1" }} />);
    const input = screen.getByRole("searchbox", { name: /Suche/ });
    expect(input).toHaveValue("Schmidt");
    expect(input).toHaveAttribute("name", "q");
    const form = container.querySelector("form");
    expect(form).toHaveAttribute("method", "get");
    expect(form).toHaveAttribute("action", "/vertraege");
    expect(container.querySelector('input[type="hidden"][name="property_id"]')).toHaveValue("p1");
  });
});
