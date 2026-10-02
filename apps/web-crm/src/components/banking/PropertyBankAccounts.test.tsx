import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PropertyBankAccounts } from "./PropertyBankAccounts";

const account = {
  id: "a1", property_id: "p1", property_number: "100", property_name: "Musterhaus", legal_entity_id: "le1", legal_entity_name: "WEG Musterhaus",
  legal_entity_kind: "weg", kind: "hoa", iban_masked: "DE** 1234", bic: null, bank_name: "Testbank", holder: "WEG Musterhaus",
  valid_from: "2026-01-01", valid_to: null, source: "manual", balance: "10.00", balance_as_of: null, balance_source: null,
  default_for_legal_entity: false, assignments: [], recent_transactions: [],
};
const entities = [{ id: "le1", kind: "weg", name: "WEG Musterhaus" }];

describe("PropertyBankAccounts", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists accounts and sets the legal entity default via PUT, then reloads", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      return Promise.resolve(jsonResponse(!init?.method && (url.includes("bank-account-options") || url.includes("banking/accounts")) ? [account] : {}));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<PropertyBankAccounts propertyId="p1" legalEntities={entities} />);
    expect(await screen.findByTestId("property-bank-accounts")).toBeInTheDocument();
    expect(fetchMock.mock.calls.map((c) => c[0])).toContain("/api/bff/properties/p1/bank-account-options");
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: /Rechtsträger/ }));
    });
    const put = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/legal-entity-default"));
    expect(put?.[0]).toBe("/api/bff/banking/accounts/a1/legal-entity-default");
    expect(JSON.parse(put?.[1]?.body as string)).toEqual({ is_default: true });
  });

  it("shows the permission message on 403 when assigning", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) =>
        Promise.resolve(init?.method === "PUT" ? jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403) : jsonResponse(url.includes("bank-account-options") ? [account] : [])),
      ),
    );
    renderIntl(<PropertyBankAccounts propertyId="p1" legalEntities={entities} />);
    await screen.findByTestId("property-bank-accounts");
    await act(async () => {
      await userEvent.click(screen.getAllByRole("button", { name: /Rechtsträger/ })[0]!);
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("shows the load error and the empty text", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(url.includes("bank-account-options") ? jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403) : jsonResponse([]))));
    renderIntl(<PropertyBankAccounts propertyId="p1" legalEntities={entities} />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByTestId("property-bank-accounts")).toBeNull();
  });
});
