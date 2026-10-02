import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { ReserveYearsTable } from "./ReserveYears";

describe("ReserveYearsTable", () => {
  it("shows opening, movements and closing per year", () => {
    renderIntl(
      <ReserveYearsTable
        rows={[
          { year: 2024, opening: "10000.00", contributions: "2000.00", contribution_basis: "paid", withdrawals: "0.00", taxes: "0.00", fees: "5.00", interest: "20.00", closing: "12015.00", source: "statement" },
          { year: 2025, opening: "12015.00", contributions: "2000.00", contribution_basis: "planned", withdrawals: "1500.00", taxes: "0.00", fees: "5.00", interest: "0.00", closing: "12510.00", source: "plan" },
        ]}
      />,
    );
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(screen.getByText(/12\.015,00/, { selector: "td.font-medium" })).toBeInTheDocument();
    expect(screen.getByText(/Wirtschaftsplan \(Soll\)/)).toBeInTheDocument();
  });

  it("shows the shared empty state without rows", () => {
    renderIntl(<ReserveYearsTable rows={[]} />);
    expect(screen.getByText("Keine Einträge vorhanden.")).toBeInTheDocument();
  });
});
