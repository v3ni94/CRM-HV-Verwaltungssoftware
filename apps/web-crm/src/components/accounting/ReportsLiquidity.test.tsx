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

  it("shows the report header, the Excel link and the number convention hint (GAH-104)", () => {
    renderIntl(
      <LiquidityReport
        ledgerId="led-1"
        data={{
          as_of: "2026-09-25",
          horizon: "2026-12-24",
          accounts: [
            { number: "001201", name: "Rücklage", balance: "500.00", kind: "reserve", kind_basis: "number_convention" },
          ],
          free_funds: "0.00",
          reserve_funds: "500.00",
          segregated_deposits: "0.00",
          expected_inflows: "0.00",
          expected_outflows: "0.00",
          projected_free_funds: "0.00",
          note: "Hinweis",
          header: {
            report: "liquidity",
            legal_entity_name: "WEG Musterstraße",
            ledger_name: "Buchungskreis",
            period_start: null,
            period_end: null,
            as_of: "2026-09-25",
            generated_at: "2026-09-25T08:00:00+00:00",
            filters: { horizon: "2026-12-24" },
            status: "draft",
            status_note: "Entwurf, keine Abrechnung",
          },
        }}
      />,
    );
    expect(screen.getByTestId("liquidity-header")).toHaveTextContent("WEG Musterstraße");
    expect(screen.getByText("Entwurf")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Als Excel herunterladen" })).toHaveAttribute(
      "href",
      "/api/bff/accounting/ledgers/led-1/reports/xlsx?report=liquidity&as_of=2026-09-25",
    );
    expect(screen.getByText(/nur nach Kontonummer 001201/)).toBeInTheDocument();
  });

  it("shows debtor credit balances as bound funds (GAK-102)", () => {
    renderIntl(
      <LiquidityReport
        data={{
          as_of: "2026-06-30",
          horizon: "2026-09-28",
          accounts: [{ number: "10000", name: "Girokonto", balance: "1000.00", kind: "free" }],
          free_funds: "1000.00",
          reserve_funds: "0.00",
          segregated_deposits: "0.00",
          expected_inflows: "0.00",
          expected_outflows: "150.00",
          debtor_credits: "120.00",
          projected_free_funds: "730.00",
          note: "",
        }}
      />,
    );
    expect(screen.getByTestId("liquidity-debtor-credits")).toHaveTextContent("120,00 EUR");
    expect(screen.getByText("730,00 EUR")).toBeInTheDocument();
  });
});
