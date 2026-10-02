import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { OwnerRentalReporting } from "./OwnerRentalReporting";

describe("owner rental reporting (GAF-34)", () => {
  it("shows rent, allocable costs and vacancy days per period", () => {
    renderIntl(
      <OwnerRentalReporting
        enabled
        note="Hinweis"
        items={[
          {
            unit_id: "u1", unit_number: "01", property_name: "Objekt",
            periods: [
              {
                statement_id: "s1", period_from: "2025-01-01", period_to: "2025-12-31",
                agreed_rent_monthly_gross: "850.00", allocable_costs_tenant: "1200.00",
                allocable_costs_property: "4800.00", vacancy_days: 31, vacancy_owner_share_property: "100.00",
              },
            ],
          },
        ]}
      />,
    );
    expect(screen.getByText("Zeitraum 01.01.2025 bis 31.12.2025")).toBeTruthy();
    expect(screen.getByText(/Leerstandstage: 31/)).toBeTruthy();
    expect(screen.getByText(/Vereinbarte Miete monatlich \(brutto\): 850,00 EUR/)).toBeTruthy();
  });

  it("shows only the note when the switch is off", () => {
    renderIntl(<OwnerRentalReporting enabled={false} note="Nicht freigegeben" items={[]} />);
    expect(screen.getByText("Nicht freigegeben")).toBeTruthy();
    expect(screen.queryByTestId("owner-reporting")).toBeNull();
  });
});
