import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { Blocks, OwnerStatementPanel } from "./OwnerStatementPanel";

const LEDGER = "0192abcd-0000-7000-8000-000000000021";
const ID = "0192abcd-0000-7000-8000-000000000022";
const RESULTS = {
  income: { rent: "1000.00", advances: "200.00", other: "0.00", total: "1200.00", lines: [] },
  expenses: { lines: [{ account_number: "040100", account_name: "Hausmeister", amount: "150.00" }], total: "150.00" },
  admin_fee: { net: "300.00", vat: "57.00", gross: "357.00", basis: "" },
  payouts: { lines: [], total: "300.00" },
  open_receivables: { total: "600.00", items: [] },
  open_payables: { total: "0.00" },
  deposits: { held: "1500.00", bank_segregated: "1500.00", difference: "0.00", items: [] },
  liquidity: { bank_total: "1650.00", deposits_held: "1500.00", open_payables: "0.00", free: "150.00" },
  operating_result: { result: "693.00" },
  sev_reconciliation: {
    hoa_cost_share: "1500.00",
    hausgeld_resolved: "1200.00",
    hausgeld_paid: "1200.00",
    hausgeld_open: "0.00",
    hoa_result: "300.00",
    tenant_allocable_costs: "900.00",
    vacancy_owner_share: "0.00",
    owner_burden: "600.00",
    hoa_statement: null,
  },
};

describe("OwnerStatementPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates a draft and calculates it", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "POST" && url.endsWith("/calculate")) {
        return jsonResponse({ id: ID, kind: "rental_owner", ledger_id: LEDGER, period_from: "2025-01-01", period_to: "2025-12-31", status: "calculated", snapshot_hash: "x", results: RESULTS, findings: [{ code: "FEE-NOT-CONFIGURED", level: "info", message: "Kein Honorar." }] });
      }
      if (init?.method === "POST") {
        return jsonResponse({ id: ID, kind: "rental_owner", ledger_id: LEDGER, period_from: "2025-01-01", period_to: "2025-12-31", status: "draft", snapshot_hash: null, results: null, findings: [] }, 201);
      }
      return jsonResponse([]);
    });
    renderIntl(<OwnerStatementPanel ledgers={[{ id: LEDGER, name: "Vermieter GmbH" }]} />);
    expect(await screen.findByText("Noch keine Eigentümerabrechnungen.")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Abrechnung anlegen"));
    expect(await screen.findByText("Noch nicht berechnet.")).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({
      ledger_id: LEDGER,
      period_from: `${new Date().getFullYear() - 1}-01-01`,
      period_to: `${new Date().getFullYear() - 1}-12-31`,
    });
    await userEvent.click(screen.getByText("Berechnen"));
    await waitFor(() => expect(screen.getByText("693,00 EUR")).toBeInTheDocument());
    expect(screen.getByText("FEE-NOT-CONFIGURED")).toBeInTheDocument();
    expect(screen.getByText(/Freigabestufe G3/)).toBeInTheDocument();
  });

  it("shows the problem message of a refused request", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) =>
      init?.method === "POST"
        ? jsonResponse({ title: "Validierung", status: 422, detail: "Zeitraum ungültig." }, 422)
        : jsonResponse([]),
    );
    renderIntl(<OwnerStatementPanel ledgers={[{ id: LEDGER, name: "Vermieter GmbH" }]} />);
    await userEvent.click(screen.getByText("Abrechnung anlegen"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Zeitraum ungültig.");
  });
});

describe("Blocks", () => {
  it("renders every block including the SEV reconciliation in euro", () => {
    renderIntl(<Blocks results={RESULTS} findings={[]} />);
    expect(screen.getByText("Überleitung WEG-Einzelabrechnung")).toBeInTheDocument();
    expect(screen.getByText("Eigentümerbelastung")).toBeInTheDocument();
    expect(screen.getAllByText("600,00 EUR").length).toBe(2); // receivables and owner burden
    expect(screen.getAllByText("1.500,00 EUR").length).toBe(4); // deposits (2), liquidity, HOA cost share
    expect(screen.getByText("Keine Auffälligkeiten.")).toBeInTheDocument();
  });
});
