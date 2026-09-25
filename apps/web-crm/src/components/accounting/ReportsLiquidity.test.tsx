import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { LiquidityReport } from "./ReportsLiquidity";

describe("LiquidityReport", () => {
  it("shows the empty state when there are no bank or cash accounts", () => {
    renderIntl(<LiquidityReport data={null} />);
    expect(screen.getByText(/Keine Bank- oder Kassenkonten/)).toBeInTheDocument();
  });

  it("renders free funds, reserves and deposits apart", () => {
    renderIntl(
      <LiquidityReport
        data={{
          as_of: "2026-09-25",
          horizon: "2026-12-24",
          accounts: [
            { number: "10000", name: "Girokonto", balance: "1000.00", kind: "free" },
            { number: "10001", name: "Rücklagenkonto", balance: "500.00", kind: "reserve" },
            { number: "10002", name: "Kautionskonto", balance: "200.00", kind: "deposit" },
          ],
          free_funds: "1000.00",
          reserve_funds: "500.00",
          segregated_deposits: "200.00",
          expected_inflows: "300.00",
          expected_outflows: "150.00",
          projected_free_funds: "850.00",
          note: "Erwartete Einzahlungen sind keine vorhandene Liquidität (nicht projiziert).",
        }}
      />,
    );
    expect(screen.getAllByText("1.000,00 EUR").length).toBeGreaterThan(0);
    expect(screen.getAllByText("500,00 EUR").length).toBeGreaterThan(0);
    expect(screen.getAllByText("200,00 EUR").length).toBeGreaterThan(0);
    expect(screen.getByText(/Girokonto/)).toBeInTheDocument();
    expect(screen.getByText(/Kautionskonto/)).toBeInTheDocument();
  });
});
