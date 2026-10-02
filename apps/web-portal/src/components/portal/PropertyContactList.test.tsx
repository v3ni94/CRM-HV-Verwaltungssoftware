import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { PropertyContactList } from "./PropertyContactList";

const row = {
  property_id: "p1",
  property_number: "0101",
  property_name: "Musterhof",
  address: "Hauptstraße 1, 10115 Berlin",
  manager_name: "Hausverwaltung Müller GmbH",
  contacts: [{ category: "caretaker", name: "Herr Hausmeister", phones: ["+49301234567"] }],
};

describe("PropertyContactList", () => {
  it("shows an empty notice without rows", () => {
    renderIntl(<PropertyContactList rows={[]} />);
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("renders property, manager and a tel link per phone number", () => {
    renderIntl(<PropertyContactList rows={[row]} />);
    expect(screen.getByText(/Musterhof/)).toBeInTheDocument();
    expect(screen.getByText("Hausverwaltung Müller GmbH")).toBeInTheDocument();
    expect(screen.getByText("Herr Hausmeister")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "+49301234567" })).toHaveAttribute("href", "tel:+49301234567");
  });

  it("falls back when manager and contacts are missing", () => {
    renderIntl(<PropertyContactList rows={[{ ...row, manager_name: null, address: null, contacts: [] }]} />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getAllByRole("definition").length).toBe(1);
  });
});
