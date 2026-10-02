import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { OwnerOverview } from "./OwnerOverview";
import { OwnerPlanList, OwnerStatementExplanations } from "./OwnerReports";

const UNIT = "00000000-0000-7000-8000-000000000002";

describe("owner reports (AF15)", () => {
  it("explains the statement with amounts and texts (GAC-03)", () => {
    renderIntl(
      <OwnerStatementExplanations
        items={[
          {
            statement_id: "s1", year: 2025, unit_id: UNIT, unit_number: "01", cost_share: "1200.00",
            advances_resolved: "1000.00", advances_paid: "900.00", result: "200.00", arrears: "100.00",
            reserve_due: "300.00", reserve_paid: "300.00", reserve_opening: "0.00", reserve_closing: "300.00",
          },
        ]}
        texts={{ portal_owner_explain_result: "Erklärung Spitze" }}
      />,
    );
    expect(screen.getByText("Erläuterung Einzelabrechnung 2025, Einheit 01")).toBeTruthy();
    expect(screen.getByText(/Abrechnungsspitze: 200,00 EUR/)).toBeTruthy();
    expect(screen.getByText("Erklärung Spitze")).toBeTruthy();
  });

  it("lists resolved plans per own unit and shows the empty note (GAF-33)", () => {
    const { unmount } = renderIntl(
      <OwnerPlanList
        items={[
          {
            plan_id: "p1", year: 2026, version: 1, title: null, valid_from: "2026-01-01",
            units: [{ unit_id: UNIT, unit_number: "01", annual: { hoa_fee: "1200.00", reserve: "300.00" },
              monthly: { hoa_fee: "100.00", reserve: "25.00" }, rounding_difference: { hoa_fee: "0.00", reserve: "0.00" } }],
          },
        ]}
        texts={{ portal_owner_explain_plan: "Plantext" }}
      />,
    );
    expect(screen.getByText("Wirtschaftsplan 2026, Version 1")).toBeTruthy();
    expect(screen.getByText("gültig ab 01.01.2026")).toBeTruthy();
    expect(screen.getByText("100,00 EUR")).toBeTruthy();
    expect(screen.getByText("Plantext")).toBeTruthy();
    unmount();
    renderIntl(<OwnerPlanList items={[]} texts={{}} />);
    expect(screen.getByText(/kein beschlossener Wirtschaftsplan/)).toBeTruthy();
  });

  it("shows a note for an empty rental income list (GAE-15)", () => {
    const { unmount } = renderIntl(<OwnerOverview payments={[]} note="" tickets={[]} income={[]} />);
    expect(screen.getByTestId("owner-income-empty").textContent).toContain("keine Mieterträge");
    unmount();
    renderIntl(<OwnerOverview payments={[]} note="" tickets={[]} income={[]} incomeNote="Schalter aus" />);
    expect(screen.getByTestId("owner-income-empty").textContent).toBe("Schalter aus");
  });
});
