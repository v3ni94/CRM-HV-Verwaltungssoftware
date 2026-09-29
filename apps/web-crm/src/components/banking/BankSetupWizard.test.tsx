import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankSetupWizard, normaliseIban, ownersFor } from "./BankSetupWizard";

const PROP_HOA = "0192abcd-0000-7000-8000-000000000001";
const PROP_RENT = "0192abcd-0000-7000-8000-000000000002";
const LINK = "0192abcd-0000-7000-8000-000000000031";
const GDWE = { id: "0192abcd-0000-7000-8000-000000000021", kind: "hoa", name: "GdWE Testweg 1" };
const OWNER = { id: "0192abcd-0000-7000-8000-000000000022", kind: "rental_owner", name: "Timo Müller" };
const MANAGER = { id: "0192abcd-0000-7000-8000-000000000023", kind: "manager", name: "Hausverwaltung Müller GmbH" };

const CONNECTION = {
  id: "0192abcd-0000-7000-8000-000000000011",
  bank_connection_id: "x",
  bank_name: "Kreissparkasse Euskirchen",
  blz: "38250110",
  bic: "WELADED1EUS",
  status: "active",
  tan_mechanism: null,
  tan_mechanisms: [],
  last_sca_at: null,
  sca_due: false,
  sca_due_on: null,
  pin_blocked: false,
  last_error: null,
  last_error_code: null,
  last_sync_at: null,
  open_session_id: null,
  accounts: [
    { id: LINK, iban_suffix: "2051", bic: "WELADED1EUS", account_number: "1", property_bank_account_id: null, balance_booked: "10.00", balance_currency: "EUR", balance_as_of: null, balance_fetched_at: null, last_transactions_fetch_at: null, last_synced_booking_date: null },
    { id: "0192abcd-0000-7000-8000-000000000032", iban_suffix: "3000", bic: null, account_number: "2", property_bank_account_id: "assigned", balance_booked: null, balance_currency: null, balance_as_of: null, balance_fetched_at: null, last_transactions_fetch_at: null, last_synced_booking_date: null },
  ],
};

type Call = { url: string; method: string; body: unknown };

function mockFetch(calls: Call[]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (url.endsWith("/banking/fints/connections")) return jsonResponse([CONNECTION]);
    if (url.startsWith("/api/bff/properties?")) return jsonResponse({ items: [{ id: PROP_HOA, number: "801", name: "Testweg 1", management_type: "hoa" }, { id: PROP_RENT, number: "802", name: "Mietstraße 2", management_type: "rental" }] });
    if (url === `/api/bff/properties/${PROP_HOA}/legal-entities`) return jsonResponse([GDWE, MANAGER]);
    if (url === `/api/bff/properties/${PROP_RENT}/legal-entities`) return jsonResponse([OWNER, MANAGER]);
    if (url.endsWith("/assign")) return jsonResponse({ id: LINK, iban_suffix: "2051", property_bank_account_id: "new" });
    if (url.endsWith("/bank-accounts") && method === "POST") return jsonResponse({ id: "new", iban_masked: "DE89 **** **** 3000" }, 201);
    return jsonResponse([]);
  });
}

describe("BankSetupWizard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("derives the legal entity from the property and kind (6.9.1)", () => {
    expect(ownersFor("hoa", [GDWE, MANAGER])).toEqual([GDWE]);
    expect(ownersFor("reserve", [GDWE, OWNER])).toEqual([GDWE]);
    expect(ownersFor("rent", [GDWE, OWNER, MANAGER])).toEqual([OWNER]);
    expect(ownersFor("deposit", [MANAGER])).toEqual([]);
    expect(normaliseIban(" de89 3704 0044 0532 0130 00 ")).toBe("DE89370400440532013000");
  });

  it("assigns an unassigned FinTS account to a property with the derived GdWE and shows what happens next", async () => {
    const calls: Call[] = [];
    mockFetch(calls);
    renderIntl(<BankSetupWizard />);
    await userEvent.click(screen.getByRole("button", { name: "Konto einrichten" }));
    expect(await screen.findByText("Kreissparkasse Euskirchen")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    // Only the account without an internal account is offered.
    expect(screen.getAllByRole("radio")).toHaveLength(1);
    await userEvent.click(screen.getByRole("radio"));
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), PROP_HOA);
    await userEvent.selectOptions(screen.getByLabelText("Kontoart"), "reserve");
    await waitFor(() => expect(screen.getByTestId("bank-setup-entity")).toHaveTextContent("GdWE: GdWE Testweg 1"));
    expect(screen.getByLabelText("Kontoinhaber")).toHaveValue("GdWE Testweg 1");
    await userEvent.click(screen.getByRole("button", { name: "Konto zuordnen" }));
    const assign = await waitFor(() => calls.find((c) => c.url.endsWith("/assign"))!);
    expect(assign.method).toBe("POST");
    expect(assign.url).toBe(`/api/bff/banking/fints/accounts/${LINK}/assign`);
    expect(assign.body).toEqual({ property_id: PROP_HOA, legal_entity_id: GDWE.id, kind: "reserve", holder: "GdWE Testweg 1" });
    expect(await screen.findByTestId("bank-setup-done")).toHaveTextContent("Konto …2051 ist als Rücklagenkonto dem Objekt 801 Testweg 1 zugeordnet.");
    expect(screen.getByText(/gegen einen Debitor \(Mieter, Eigentümer\) oder einen Kreditor/)).toBeInTheDocument();
  });

  it("creates the internal account for the file path with the owner of a rental property", async () => {
    const calls: Call[] = [];
    mockFetch(calls);
    renderIntl(<BankSetupWizard />);
    await userEvent.click(screen.getByRole("button", { name: "Konto einrichten" }));
    await screen.findByText("Kreissparkasse Euskirchen");
    await userEvent.click(screen.getByRole("radio", { name: /Kontoauszug als Datei/ }));
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    const next = screen.getByRole("button", { name: "Weiter" });
    expect(next).toBeDisabled();
    await userEvent.type(screen.getByLabelText("IBAN"), "de89 3704 0044 0532 0130 00");
    await userEvent.type(screen.getByLabelText("Bank"), "Volksbank");
    expect(next).toBeEnabled();
    await userEvent.click(next);
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), PROP_RENT);
    await userEvent.selectOptions(screen.getByLabelText("Kontoart"), "rent");
    await waitFor(() => expect(screen.getByTestId("bank-setup-entity")).toHaveTextContent("Eigentümer: Timo Müller"));
    // A deposit account of an HOA-only property has no owner: the hint appears.
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), PROP_HOA);
    await waitFor(() => expect(screen.getByTestId("bank-setup-entity")).toHaveTextContent("keinen passenden Rechtsträger"));
    expect(screen.getByRole("button", { name: "Konto zuordnen" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), PROP_RENT);
    await waitFor(() => expect(screen.getByLabelText("Kontoinhaber")).toHaveValue("Timo Müller"));
    await userEvent.click(screen.getByRole("button", { name: "Konto zuordnen" }));
    const created = await waitFor(() => calls.find((c) => c.method === "POST" && c.url.endsWith("/bank-accounts"))!);
    expect(created.url).toBe(`/api/bff/properties/${PROP_RENT}/bank-accounts`);
    expect(created.body).toMatchObject({ legal_entity_id: OWNER.id, kind: "rent", iban: "DE89370400440532013000", holder: "Timo Müller", bank_name: "Volksbank" });
    expect(await screen.findByTestId("bank-setup-done")).toHaveTextContent("DE89 **** **** 3000");
    expect(screen.getByText(/unter Kontoauszug hochgeladen/)).toBeInTheDocument();
  });
});
