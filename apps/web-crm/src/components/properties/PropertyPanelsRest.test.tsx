import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { PortalDocumentsPanel, SubCommunitiesPanel } from "./PropertyPanels";

describe("SubCommunitiesPanel", () => {
  it("lists code, name and notes", () => {
    renderIntl(<SubCommunitiesPanel rows={[{ id: "1", code: "TG", name: "Tiefgarage", notes: "Haus 2" }]} />);
    expect(screen.getByTestId("property-sub-communities")).toHaveTextContent("TG Tiefgarage, Haus 2");
  });

  it("shows the empty text", () => {
    renderIntl(<SubCommunitiesPanel rows={[]} />);
    expect(screen.getByText("Keine Untergemeinschaften angelegt.")).toBeInTheDocument();
  });
});

describe("PortalDocumentsPanel", () => {
  it("sorts by sort_order and maps visibility labels", () => {
    renderIntl(
      <PortalDocumentsPanel
        rows={[
          { id: "2", document_id: "d2", title: "Zweites", visible_for: [], sort_order: 2 },
          { id: "1", document_id: "d1", title: "Erstes", visible_for: ["tenant", "owner"], sort_order: 1 },
        ]}
      />,
    );
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Erstes");
    expect(rows[0]).toHaveTextContent("Mieter, Eigentümer");
    expect(rows[1]).toHaveTextContent("niemand");
    expect(screen.getByRole("link", { name: "Erstes" })).toHaveAttribute("href", "/dokumente/d1");
  });

  it("shows the empty text", () => {
    renderIntl(<PortalDocumentsPanel rows={[]} />);
    expect(screen.getByText("Keine Dokumente in der Objektmappe.")).toBeInTheDocument();
  });
});
