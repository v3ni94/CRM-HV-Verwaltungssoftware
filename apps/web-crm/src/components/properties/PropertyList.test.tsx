import { screen, within } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { PropertyList } from "./PropertyList";

const ROWS = [
  {
    id: "p1",
    number: "216",
    name: "Haagstraße 32",
    management_type: "rental",
    status: "active",
    owner_missing: true,
  },
  {
    id: "p2",
    number: "217",
    name: "Weg 2",
    management_type: "rental",
    status: "active",
    owner_missing: false,
  },
  {
    id: "p3",
    number: "336",
    name: "Gladbacher Straße 95",
    management_type: "hoa",
    status: "active",
    owner_missing: false,
  },
  {
    id: "p4",
    number: "401",
    name: "Alte Straße 1",
    management_type: "hoa",
    status: "terminated",
    owner_missing: false,
  },
];

describe("PropertyList", () => {
  it("marks rental properties without owner in table and cards", () => {
    renderIntl(<PropertyList rows={ROWS} />);
    const table = screen.getByTestId("properties");
    expect(within(table).getByText("Eigentümer")).toBeInTheDocument();
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[0]!).getByText("Eigentümer fehlt")).toBeInTheDocument();
    expect(within(rows[1]!).queryByText("Eigentümer fehlt")).toBeNull();
    expect(within(rows[2]!).queryByText("Eigentümer fehlt")).toBeNull();
    const cards = screen.getAllByTestId("property-card");
    expect(within(cards[0]!).getByText("Eigentümer fehlt")).toBeInTheDocument();
    expect(within(cards[1]!).queryByText("Eigentümer fehlt")).toBeNull();
  });

  it("greys out deactivated properties and labels them with the status chip", () => {
    renderIntl(<PropertyList rows={ROWS} />);
    const table = screen.getByTestId("properties");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows[3]).toHaveAttribute("data-status", "terminated");
    expect(rows[3]!.className).toContain("opacity-60");
    expect(rows[0]!.className).not.toContain("opacity-60");
    expect(within(rows[3]!).getByText("Deaktiviert")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("Aktiv")).toBeInTheDocument();
    const cards = screen.getAllByTestId("property-card");
    expect(cards[3]).toHaveAttribute("data-status", "terminated");
    expect(within(cards[3]!).getByText("Deaktiviert")).toBeInTheDocument();
  });
});
