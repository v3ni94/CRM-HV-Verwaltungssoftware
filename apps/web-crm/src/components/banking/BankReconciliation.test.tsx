import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankReconciliation } from "./BankReconciliation";

const PBA = "0192abcd-0000-7000-8000-000000000031";
const accounts = [
  { id: PBA, property_id: "p1", property_number: "0001", property_name: "Haus", legal_entity_id: "le1", legal_entity_name: "WEG Haus", kind: "hoa", iban_masked: "DE12****1234", bank_name: "Sparkasse", holder: "WEG" },
];

describe("BankReconciliation", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows statement and ledger differences per statement and counts findings (B09)", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url.endsWith(`/banking/accounts/${PBA}/reconciliation`)) {
        return jsonResponse([
          { statement_id: "s1", statement_ref: "2026/09", closing_date: "2026-09-30", opening_balance: "1000.00", movements: "250.00", closing_balance: "1250.00", statement_difference: "0.00", ledger_balance: "1250.00", ledger_difference: "0.00" },
          { statement_id: "s2", statement_ref: "2026/10", closing_date: "2026-10-31", opening_balance: "1250.00", movements: "-100.00", closing_balance: "1160.00", statement_difference: "10.00", ledger_balance: null, ledger_difference: null },
        ]);
      }
      if (url.includes("/banking/accounts")) return jsonResponse(accounts);
      return jsonResponse({}, 404);
    });
    renderIntl(<BankReconciliation />);
    await userEvent.selectOptions(await screen.findByLabelText("Bankkonto"), PBA);
    await waitFor(() => expect(screen.getByTestId("reconciliation-summary")).toHaveTextContent("1 Auszug mit Differenz."));
    expect(screen.getByText("2026/09")).toBeInTheDocument();
    expect(screen.getAllByText("1.250,00 EUR").length).toBeGreaterThan(0);
    expect(screen.getByText("10,00 EUR")).toHaveClass("text-danger-fg");
    expect(screen.getAllByText("nicht ermittelbar")).toHaveLength(2);
    expect(calls.some((url) => url.endsWith(`/banking/accounts/${PBA}/reconciliation`))).toBe(true);
  });

  it("counts several statements with a difference in the plural", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/reconciliation")) {
        return jsonResponse([
          { statement_id: "s1", statement_ref: "2026/09", closing_date: "2026-09-30", opening_balance: "1000.00", movements: "250.00", closing_balance: "1250.00", statement_difference: "0.00", ledger_balance: "250.00", ledger_difference: "1000.00" },
          { statement_id: "s2", statement_ref: "2026/10", closing_date: "2026-10-31", opening_balance: "1250.00", movements: "-100.00", closing_balance: "1160.00", statement_difference: "10.00", ledger_balance: null, ledger_difference: null },
        ]);
      }
      return jsonResponse(accounts);
    });
    renderIntl(<BankReconciliation />);
    await userEvent.selectOptions(await screen.findByLabelText("Bankkonto"), PBA);
    await waitFor(() => expect(screen.getByTestId("reconciliation-summary")).toHaveTextContent("2 Auszüge mit Differenz."));
  });

  it("shows chain breaks, period gaps and statements without balances (GAH-102)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/reconciliation")) {
        return jsonResponse([
          { statement_id: "s1", statement_ref: "2026/01", closing_date: "2026-01-31", opening_balance: "1000.00", movements: "100.00", closing_balance: "1100.00", statement_difference: "0.00", ledger_balance: null, ledger_difference: null, status: "ok", chain_status: "first", chain_difference: null, period_status: "first", gap_from: null, gap_to: null },
          { statement_id: "s2", statement_ref: "2026/02", closing_date: "2026-02-28", opening_balance: "1150.00", movements: "50.00", closing_balance: "1200.00", statement_difference: "0.00", ledger_balance: null, ledger_difference: null, status: "ok", chain_status: "break", chain_difference: "50.00", period_status: "ok", gap_from: null, gap_to: null },
          { statement_id: "s3", statement_ref: "CSV", closing_date: null, opening_balance: null, movements: "10.00", closing_balance: null, statement_difference: null, ledger_balance: null, ledger_difference: null, status: "not_checkable", chain_status: "not_checkable", chain_difference: null, period_status: "gap", gap_from: "2026-03-01", gap_to: "2026-03-31" },
        ]);
      }
      return jsonResponse(accounts);
    });
    renderIntl(<BankReconciliation />);
    await userEvent.selectOptions(await screen.findByLabelText("Bankkonto"), PBA);
    await waitFor(() => expect(screen.getByTestId("reconciliation-chain-summary")).toHaveTextContent("2 Auszüge mit Kettenbruch oder Zeitraumlücke."));
    expect(screen.getByText("Kettenbruch 50,00 EUR")).toHaveClass("text-danger-fg");
    expect(screen.getByText("Kette nicht prüfbar (Salden fehlen), Lücke 01.03.2026 bis 31.03.2026")).toBeInTheDocument();
    expect(screen.getByTestId("reconciliation-not-checkable")).toHaveTextContent("1 Auszug ohne Salden, nicht prüfbar (z. B. CSV).");
  });

  it("reports an empty account", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/reconciliation")) return jsonResponse([]);
      return jsonResponse(accounts);
    });
    renderIntl(<BankReconciliation />);
    await userEvent.selectOptions(await screen.findByLabelText("Bankkonto"), PBA);
    expect(await screen.findByText("Für dieses Konto liegen keine Auszüge vor.")).toBeInTheDocument();
  });
});
