import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AdminFeePostingConfigForm, type PostingConfig } from "./AdminFeePostingConfigForm";

const L1 = "0192abcd-0000-7000-8000-000000000a01";
const A = (id: string, number: string, name: string, active = true) => ({ id, number, name, active });
const ACCOUNTS = [
  A("a1", "120000", "Forderungen Honorar"),
  A("a2", "840000", "Erlöse Honorar"),
  A("a3", "177600", "Umsatzsteuer"),
  A("a4", "999999", "Inaktiv", false),
];

describe("AdminFeePostingConfigForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the accounts of the chosen ledger, hides inactive ones and saves the assignment", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(async () => jsonResponse(ACCOUNTS))
      .mockImplementationOnce(async () => jsonResponse({ id: "c1" }));
    renderIntl(<AdminFeePostingConfigForm ledgers={[{ id: L1, label: "HVM Buchungskreis" }]} initial={null} canUpdate />);
    expect(screen.getByText(/Noch keine Kontenzuordnung/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zuordnung speichern" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Buchungskreis des Verwalters"), L1);
    expect((await screen.findAllByRole("option", { name: "840000 Erlöse Honorar" })).length).toBe(3);
    expect(screen.queryByRole("option", { name: /Inaktiv/ })).toBeNull();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/accounting/ledgers/${L1}/accounts`);
    await userEvent.selectOptions(screen.getByLabelText("Forderungskonto"), "a1");
    await userEvent.selectOptions(screen.getByLabelText("Erlöskonto"), "a2");
    await userEvent.type(screen.getByLabelText("Aufwandskonto (Nummer)"), "4100");
    expect(screen.getByText("Kontonummern bestehen aus genau sechs Ziffern.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Aufwandskonto (Nummer)"), "00");
    await userEvent.type(screen.getByLabelText("Verbindlichkeitskonto (Nummer)"), "160000");
    await userEvent.click(screen.getByRole("button", { name: "Zuordnung speichern" }));
    await waitFor(() => expect(screen.getByText("Kontenzuordnung gespeichert.")).toBeInTheDocument());
    const [url, init] = fetchMock.mock.calls[1] ?? [];
    expect(url).toBe("/api/bff/accounting/admin-fee-posting-config");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(init?.body as string)).toEqual({
      manager_ledger_id: L1,
      manager_receivable_account_id: "a1",
      manager_revenue_account_id: "a2",
      manager_vat_account_id: null,
      payer_expense_account_number: "410000",
      payer_payable_account_number: "160000",
      payer_vat_account_number: null,
    });
  });

  it("blocks identical accounts on both sides", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(ACCOUNTS));
    const initial: PostingConfig = {
      manager_ledger_id: L1,
      manager_receivable_account_id: "a1",
      manager_revenue_account_id: "a2",
      manager_vat_account_id: null,
      payer_expense_account_number: "410000",
      payer_payable_account_number: "160000",
      payer_vat_account_number: null,
    };
    renderIntl(<AdminFeePostingConfigForm ledgers={[{ id: L1, label: "HVM" }]} initial={initial} canUpdate />);
    const save = screen.getByRole("button", { name: "Zuordnung speichern" });
    expect(save).toBeEnabled();
    await userEvent.type(screen.getByLabelText("Vorsteuerkonto (Nummer, optional)"), "410000");
    expect(screen.getByText("Die Kontonummern der Zahlerseite müssen verschieden sein.")).toBeInTheDocument();
    expect(save).toBeDisabled();
    await screen.findAllByRole("option", { name: "177600 Umsatzsteuer" });
    await userEvent.selectOptions(screen.getByLabelText("Umsatzsteuerkonto (optional)"), "a1");
    expect(screen.getByText("Die Konten der Verwalterseite müssen verschieden sein.")).toBeInTheDocument();
  });

  it("is read only without the approval permission and shows the API problem on save failure", async () => {
    const view = renderIntl(<AdminFeePostingConfigForm ledgers={[{ id: L1, label: "HVM" }]} initial={null} canUpdate={false} />);
    expect(screen.queryByRole("button", { name: "Zuordnung speichern" })).toBeNull();
    expect(screen.getByLabelText("Buchungskreis des Verwalters")).toBeDisabled();
    view.unmount();
    const init: PostingConfig = {
      manager_ledger_id: L1,
      manager_receivable_account_id: "a1",
      manager_revenue_account_id: "a2",
      manager_vat_account_id: null,
      payer_expense_account_number: "410000",
      payer_payable_account_number: "160000",
      payer_vat_account_number: null,
    };
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(async () => jsonResponse(ACCOUNTS))
      .mockImplementationOnce(async () => jsonResponse({ title: "Falscher Rechtsträger", status: 422, detail: "Der Erlös wird nur im Buchungskreis eines Verwalter-Rechtsträgers gebucht." }, 422));
    renderIntl(<AdminFeePostingConfigForm ledgers={[{ id: L1, label: "HVM" }]} initial={init} canUpdate />);
    await userEvent.click(screen.getByRole("button", { name: "Zuordnung speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Verwalter-Rechtsträger/);
  });
});
