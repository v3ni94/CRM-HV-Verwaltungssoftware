import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { pdfHref, StaffProtocolList, type StaffProtocol } from "./StaffProtocolList";

function row(overrides: Partial<StaffProtocol> = {}): StaffProtocol {
  return {
    id: "11111111-1111-7111-8111-111111111111",
    number: "UP-20260926-001",
    version: 1,
    kind: "rental",
    status: "in_progress",
    handover_date: "2026-09-01",
    address: "Portalweg 7, 40789 Monheim am Rhein",
    property: { id: "p1", number: "832", name: "Portalhaus" },
    unit: { id: "u1", number: "07", label: null },
    unit_number: "07",
    unit_label: null,
    floor: null,
    external_object_number: null,
    finalized: false,
    pdf_url: "/api/v1/portal/handover-protocols/11111111-1111-7111-8111-111111111111/pdf",
    ...overrides,
  };
}

describe("StaffProtocolList", () => {
  it("shows object, unit, date, status and links", () => {
    renderIntl(<StaffProtocolList rows={[row()]} />);
    expect(screen.getByText("UP-20260926-001")).toBeInTheDocument();
    expect(screen.getByText("832 Portalhaus")).toBeInTheDocument();
    expect(screen.getByText("07")).toBeInTheDocument();
    expect(screen.getByText("01.09.2026")).toBeInTheDocument();
    expect(screen.getByText("In Bearbeitung")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Protokoll öffnen" })).toHaveAttribute(
      "href",
      "/uebergabe/11111111-1111-7111-8111-111111111111",
    );
    expect(screen.getByRole("link", { name: "PDF öffnen" })).toHaveAttribute(
      "href",
      "/api/portal-files/portal/handover-protocols/11111111-1111-7111-8111-111111111111/pdf",
    );
  });

  it("labels a manual object and an empty list", () => {
    renderIntl(
      <StaffProtocolList
        rows={[row({ property: null, unit: null, external_object_number: "EXT-9", version: 2 })]}
      />,
    );
    expect(screen.getByText("Objekt manuell erfasst EXT-9")).toBeInTheDocument();
    expect(screen.getByText("UP-20260926-001 Version 2")).toBeInTheDocument();
    renderIntl(<StaffProtocolList rows={[]} />);
    expect(screen.getByText("Keine Übergabeprotokolle vorhanden.")).toBeInTheDocument();
  });

  it("maps the API pdf path onto the file proxy", () => {
    expect(pdfHref(row())).toBe(
      "/api/portal-files/portal/handover-protocols/11111111-1111-7111-8111-111111111111/pdf",
    );
  });
});
