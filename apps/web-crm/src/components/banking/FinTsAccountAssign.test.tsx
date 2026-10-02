import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankSetupWizard } from "./BankSetupWizard";
import { FinTsCreateInternalForm, type FinTsAccount } from "./FinTsConnections";

const PROP = "0192abcd-0000-7000-8000-0000000000a1";
const LINK = "0192abcd-0000-7000-8000-0000000000a2";
const GDWE = { id: "0192abcd-0000-7000-8000-0000000000a3", kind: "hoa", name: "GdWE Testweg 1" };
const MANAGER = { id: "0192abcd-0000-7000-8000-0000000000a4", kind: "manager", name: "Hausverwaltung Müller GmbH" };

const ACCOUNT: FinTsAccount = {
  id: LINK, iban_suffix: "2051", bic: null, account_number: "1", property_bank_account_id: null,
  balance_booked: null, balance_currency: null, balance_as_of: null, balance_fetched_at: null,
  last_transactions_fetch_at: null, last_synced_booking_date: null,
};
const CONNECTION = {
  id: "c1", bank_connection_id: "x", bank_name: "Kreissparkasse Euskirchen", blz: "38250110", bic: null,
  status: "active", tan_mechanism: null, tan_mechanisms: [], last_sca_at: null, sca_due: false, sca_due_on: null,
  pin_blocked: false, last_error: null, last_error_code: null, last_sync_at: null, open_session_id: null,
  accounts: [ACCOUNT],
};

type Call = { url: string; method: string; body: unknown };

function mockFetch(calls: Call[], assign: () => Response) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
    if (url.endsWith("/banking/fints/connections")) return jsonResponse([CONNECTION]);
    if (url.startsWith("/api/bff/properties?")) return jsonResponse({ items: [{ id: PROP, number: "801", name: "Testweg 1", management_type: "hoa" }] });
    if (url === `/api/bff/properties/${PROP}/legal-entities`) return jsonResponse([GDWE, MANAGER]);
    if (url.endsWith("/assign")) return assign();
    return jsonResponse([]);
  });
}

describe("FinTS account assignment (GAG-01, GAG-02)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("creates the internal account inline with the owner derived from property and kind", async () => {
    const calls: Call[] = [];
    mockFetch(calls, () => jsonResponse({ id: LINK, property_bank_account_id: "new" }));
    const onDone = vi.fn();
    renderIntl(<FinTsCreateInternalForm link={ACCOUNT} defaultHolder="" onDone={onDone} />);
    await screen.findByRole("option", { name: "801 Testweg 1" });
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), PROP);
    await userEvent.selectOptions(screen.getByLabelText("Kontoart"), "reserve");
    await waitFor(() => expect(screen.getByLabelText("Rechtsträger")).toHaveValue(GDWE.id));
    // The manager is never offered as owner of a reserve account (6.9.1).
    expect(screen.queryByRole("option", { name: /Hausverwaltung Müller GmbH/ })).toBeNull();
    expect(screen.getByLabelText("Kontoinhaber")).toHaveValue("GdWE Testweg 1");
    await userEvent.click(screen.getByRole("button", { name: "Anlegen und zuordnen" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const call = calls.find((c) => c.url.endsWith("/assign"))!;
    expect(call.url).toBe(`/api/bff/banking/fints/accounts/${LINK}/assign`);
    expect(call.method).toBe("POST");
    expect(call.body).toEqual({ property_id: PROP, legal_entity_id: GDWE.id, kind: "reserve", holder: "GdWE Testweg 1" });
  });

  it("offers the account kind other with every legal entity as possible owner (GAH-404)", async () => {
    const calls: Call[] = [];
    mockFetch(calls, () => jsonResponse({ id: LINK, property_bank_account_id: "new" }));
    renderIntl(<FinTsCreateInternalForm link={ACCOUNT} defaultHolder="" onDone={() => {}} />);
    await screen.findByRole("option", { name: "801 Testweg 1" });
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), PROP);
    expect(screen.getByRole("option", { name: "Sonstiges Konto" })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Kontoart"), "other");
    await userEvent.selectOptions(screen.getByLabelText("Rechtsträger"), MANAGER.id);
    await userEvent.click(screen.getByRole("button", { name: "Anlegen und zuordnen" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/assign"))).toBe(true));
    const call = calls.find((c) => c.url.endsWith("/assign"))!;
    expect(call.body).toMatchObject({ kind: "other", legal_entity_id: MANAGER.id });
  });

  it("shows the API error text and keeps the form open", async () => {
    const calls: Call[] = [];
    mockFetch(calls, () => jsonResponse({ title: "Ungültig", detail: "Der Rechtsträger gehört nicht zu diesem Objekt.", code: "MHVP-VAL-0001" }, 422));
    const onDone = vi.fn();
    renderIntl(<FinTsCreateInternalForm link={ACCOUNT} defaultHolder="" onDone={onDone} />);
    await screen.findByRole("option", { name: "801 Testweg 1" });
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), PROP);
    await waitFor(() => expect(screen.getByLabelText("Rechtsträger")).toHaveValue(GDWE.id));
    await userEvent.click(screen.getByRole("button", { name: "Anlegen und zuordnen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Der Rechtsträger gehört nicht zu diesem Objekt.");
    expect(onDone).not.toHaveBeenCalled();
  });

  it("opens the wizard from the deep link with the FinTS account preselected at step 3", async () => {
    window.history.replaceState(null, "", `/bank?setup=fints&link=${LINK}`);
    const calls: Call[] = [];
    mockFetch(calls, () => jsonResponse({ id: LINK, iban_suffix: "2051", property_bank_account_id: "new" }));
    renderIntl(<BankSetupWizard />);
    const property = await screen.findByLabelText("Objekt");
    expect(screen.getByText(/Objekt und Kontoart/, { selector: "[aria-current='step']" })).toBeInTheDocument();
    await userEvent.selectOptions(property, PROP);
    await waitFor(() => expect(screen.getByTestId("bank-setup-entity")).toHaveTextContent("GdWE Testweg 1"));
    await userEvent.click(screen.getByRole("button", { name: "Konto zuordnen" }));
    const assign = await waitFor(() => calls.find((c) => c.url.endsWith("/assign"))!);
    expect(assign.url).toBe(`/api/bff/banking/fints/accounts/${LINK}/assign`);
  });
});
