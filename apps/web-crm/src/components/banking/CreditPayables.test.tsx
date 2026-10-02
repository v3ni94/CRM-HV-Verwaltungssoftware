import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import {
  CreditPayables,
  type CreditPayableCandidate,
  type CreditPayableRow,
  type CreditPayableSettings,
} from "./CreditPayables";

const settingsOff: CreditPayableSettings = {
  mode: "off",
  four_eyes_required: true,
  creditor_account_number: null,
  owner_debit_account_number: null,
  deposit_debit_account_number: null,
  modes: ["off", "subledger", "reclass"],
  decision_ref: "Q01-01",
  note: "Buchungsregel offen",
};
const candidate: CreditPayableCandidate = {
  source_type: "rent_statement",
  source_id: "00000000-0000-7000-8000-000000000001",
  contract_id: "00000000-0000-7000-8000-000000000002",
  ledger_id: "00000000-0000-7000-8000-000000000003",
  amount: "80.00",
  label: "Guthaben aus Betriebskostenabrechnung 2025",
  reference_date: "2026-10-01",
  source_entry_id: null,
  payout_reason: "statement_credit",
};
const row = (over: Partial<CreditPayableRow>): CreditPayableRow => ({
  id: "00000000-0000-7000-8000-0000000000aa",
  source_type: "rent_statement",
  source_id: candidate.source_id,
  contract_id: candidate.contract_id,
  amount: "80.00",
  variant: "subledger",
  status: "released",
  state: "open",
  remaining: "80.00",
  reclass_entry_id: null,
  payment_order_id: null,
  warnings: [],
  ...over,
});

function route(responses: Record<string, unknown>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    const key = `${method} ${url}`;
    const body = responses[key] ?? responses[url];
    return jsonResponse(body ?? [], method === "POST" ? 201 : 200);
  });
}

describe("CreditPayables", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows candidates with the switch off and saves the variant", async () => {
    const fetchMock = route({
      "/api/bff/accounting/credit-payables/settings": settingsOff,
      "/api/bff/accounting/credit-payables/candidates": [candidate],
      "/api/bff/accounting/credit-payables": [],
    });
    renderIntl(<CreditPayables />);
    expect(await screen.findByText("Guthaben aus Betriebskostenabrechnung 2025")).toBeInTheDocument();
    expect(screen.getByText(/Buchungsregel offen \(Q01-01\)/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Vorschlagen" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Variante"), "subledger");
    await userEvent.click(screen.getByRole("button", { name: "Einstellungen speichern" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Einstellungen gespeichert."));
    const put = fetchMock.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "PUT");
    expect(JSON.parse(String((put?.[1] as RequestInit).body))).toEqual({ mode: "subledger", four_eyes_required: true });
  });

  it("releases a proposal and creates a payout order from an open payable", async () => {
    const proposed = row({ id: "00000000-0000-7000-8000-0000000000bb", status: "proposed", state: "proposed" });
    const open = row({ warnings: [{ code: "OPEN_RECEIVABLES", message: "Offene Forderungen des Vertrags 10.00 EUR" }] });
    const fetchMock = route({
      "/api/bff/accounting/credit-payables/settings": { ...settingsOff, mode: "subledger" },
      "/api/bff/accounting/credit-payables/candidates": [],
      "/api/bff/accounting/credit-payables": [proposed, open],
      [`/api/bff/accounting/credit-payables/${open.id}/payout-options`]: {
        payees: [{ id: "p1", holder: "Mieter Test", iban_suffix: "3000" }],
        bank_accounts: [{ id: "b1", holder: "Vermieter", iban_suffix: "2051" }],
      },
      [`POST /api/bff/accounting/credit-payables/${open.id}/payment-order`]: { id: "o1" },
      [`POST /api/bff/accounting/credit-payables/${proposed.id}/release`]: proposed,
    });
    renderIntl(<CreditPayables />);
    expect(await screen.findByText("Offene Forderungen des Vertrags 10.00 EUR")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Freigeben" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Freigegeben."));
    await userEvent.click(screen.getByRole("button", { name: "Zahlungsauftrag" }));
    await userEvent.click(await screen.findByRole("button", { name: "Auftrag anlegen" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Zahlungsauftrag als Entwurf angelegt"));
    const order = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/payment-order"));
    const body = JSON.parse(String((order?.[1] as RequestInit).body));
    expect(body.contact_bank_account_id).toBe("p1");
    expect(body.property_bank_account_id).toBe("b1");
  });

  it("withdraws with a reason", async () => {
    const open = row({});
    vi.spyOn(window, "prompt").mockReturnValue("Verrechnung statt Auszahlung");
    const fetchMock = route({
      "/api/bff/accounting/credit-payables/settings": { ...settingsOff, mode: "subledger" },
      "/api/bff/accounting/credit-payables/candidates": [],
      "/api/bff/accounting/credit-payables": [open],
      [`POST /api/bff/accounting/credit-payables/${open.id}/withdraw`]: { ...open, status: "withdrawn" },
    });
    renderIntl(<CreditPayables />);
    await userEvent.click(await screen.findByRole("button", { name: "Zurücknehmen" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Zurückgenommen."));
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/withdraw"));
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({ reason: "Verrechnung statt Auszahlung" });
  });

  it("sends contract_id with source_type deposit_settlement when proposing (GAH-406)", async () => {
    const deposit: CreditPayableCandidate = {
      ...candidate,
      source_type: "deposit_settlement",
      label: "Kautionsabrechnung Guthaben",
      payout_reason: "deposit_credit",
    } as CreditPayableCandidate;
    const fetchMock = route({
      "/api/bff/accounting/credit-payables/settings": { ...settingsOff, mode: "subledger" },
      "/api/bff/accounting/credit-payables/candidates": [deposit],
      "/api/bff/accounting/credit-payables": [],
      "POST /api/bff/accounting/credit-payables": row({ status: "proposed", state: "proposed" }),
    });
    renderIntl(<CreditPayables />);
    await userEvent.click(await screen.findByRole("button", { name: "Vorschlagen" }));
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => (c[1] as RequestInit | undefined)?.method === "POST")).toBe(true));
    const post = fetchMock.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "POST")!;
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({
      source_type: "deposit_settlement",
      source_id: deposit.source_id,
      contract_id: deposit.contract_id,
    });
  });
});
