import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { RelationsPanel, type ObjectRelation } from "./RelationsPanel";

const base: ObjectRelation = {
  kind: "mieter",
  property_id: "11111111-1111-1111-1111-111111111111",
  property_name: "Hauptstraße 1",
  property_city: "Hilden",
  unit_id: "22222222-2222-2222-2222-222222222222",
  unit_label: "W01",
  valid_from: "2021-01-01",
  valid_to: null,
  active: true,
  source: "contract",
  contract_id: "33333333-3333-3333-3333-333333333333",
  category_code: null,
};

describe("RelationsPanel", () => {
  it("shows the empty state", () => {
    renderIntl(<RelationsPanel relations={[]} />);
    expect(screen.getByText("Keine Objektbezüge hinterlegt.")).toBeInTheDocument();
  });

  it("renders object link, unit, role, period and status", () => {
    renderIntl(
      <RelationsPanel
        relations={[
          base,
          { ...base, kind: "eigentuemer", source: "property_owner", unit_id: null, unit_label: null, contract_id: null, valid_from: "2015-03-01", valid_to: "2020-12-31", active: false },
          { ...base, kind: "kontakt", source: "property_contact", unit_id: null, unit_label: null, contract_id: null, category_code: "hausmeister" },
        ]}
      />,
    );
    expect(screen.getByText("Beziehungen zu Objekten und Einheiten")).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: "Hauptstraße 1" });
    expect(links[0]).toHaveAttribute("href", `/objekte/${base.property_id}`);
    expect(screen.getByText("W01")).toBeInTheDocument();
    expect(screen.getByText("Mieter")).toBeInTheDocument();
    expect(screen.getByText("Eigentümer")).toBeInTheDocument();
    expect(screen.getByText("hausmeister")).toBeInTheDocument();
    expect(screen.getAllByText("seit 01.01.2021")).toHaveLength(2);
    expect(screen.getByText("01.03.2015 bis 31.12.2020")).toBeInTheDocument();
    expect(screen.getByText("beendet")).toBeInTheDocument();
    expect(screen.getAllByText("aktiv")).toHaveLength(2);
  });
});
