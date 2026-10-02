import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankAccountOverview } from "./BankAccountOverview";

const account = {
  id: "a1", property_id: "p1", property_number: "100", property_name: "Musterhaus", legal_entity_id: "le1", legal_entity_name: "WEG Musterhaus",
  legal_entity_kind: "weg", kind: "hoa", iban_masked: "DE** 1234", bic: null, bank_name: "Testbank", holder: "WEG Musterhaus",
  valid_from: "2026-01-01", valid_to: null, source: "manual", balance: "10.00", balance_as_of: null, balance_source: null,
  default_for_legal_entity: false, assignments: [], recent_transactions: [],
};

describe("BankAccountOverview", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads properties and accounts and filters by property via the BFF", async () => {
    const fetchMock = vi.fn((url: string) =>
      Promise.resolve(url.startsWith("/api/bff/properties") ? jsonResponse({ items: [{ id: "p1", number: "100", name: "Musterhaus" }] }) : jsonResponse([account])),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<BankAccountOverview />);
    expect(await screen.findByRole("option", { name: "100 Musterhaus" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("option", { name: "WEG Musterhaus" })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getAllByRole("combobox")[0]!, "p1");
    await waitFor(() => expect(fetchMock.mock.calls.map((c) => c[0])).toContain("/api/bff/banking/accounts?property_id=p1"));
    expect(screen.queryByTestId("bank-account-card")).toBeNull();
  });

  it("shows the error when accounts are forbidden (403)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        Promise.resolve(url.startsWith("/api/bff/properties") ? jsonResponse({ items: [] }) : jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)),
      ),
    );
    renderIntl(<BankAccountOverview />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
