import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { BuildingsPanel, ServiceProvidersPanel } from "./PropertyPanels";

describe("BuildingsPanel", () => {
  it("shows the empty text without buildings", () => {
    renderIntl(<BuildingsPanel buildings={[]} />);
    expect(screen.getByText("Keine Gebäude angelegt.")).toBeInTheDocument();
  });

  it("joins the address and marks a missing energy certificate", () => {
    renderIntl(<BuildingsPanel buildings={[{ id: "b1", property_id: "p1", name: "Haus B", street: "Rheinallee", house_number: "12", floors: 4 }]} />);
    expect(screen.getByRole("link", { name: "Gebäude öffnen: Haus B" })).toHaveAttribute("href", "/objekte/p1/gebaeude/b1");
    expect(screen.getByText("Rheinallee 12")).toBeInTheDocument();
    expect(screen.getByTestId("property-buildings")).toBeInTheDocument();
  });
});

describe("ServiceProvidersPanel", () => {
  it("shows the empty text without rows", () => {
    renderIntl(<ServiceProvidersPanel rows={[]} />);
    expect(screen.getByText("Keine Dienstleisterverhältnisse hinterlegt.")).toBeInTheDocument();
  });

  it("falls back to ids, shows the end date and the unknown exemption status", () => {
    renderIntl(
      <ServiceProvidersPanel rows={[{ id: "s1", contact_id: "c-5", contract_type_code: "reinigung", valid_from: "2024-01-01", valid_to: "2025-06-30", creditor_account_id: "acc-9" }]} />,
    );
    expect(screen.getByRole("link", { name: "c-5" })).toHaveAttribute("href", "/kontakte/c-5");
    expect(screen.getByText(/01.01.2024.*30.06.2025/)).toBeInTheDocument();
    expect(screen.getByText("nicht erfasst")).toBeInTheDocument();
    expect(screen.getByText("acc-9")).toBeInTheDocument();
  });
});
