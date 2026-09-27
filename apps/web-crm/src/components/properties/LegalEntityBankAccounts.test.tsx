import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LegalEntityBankAccounts, type LegalEntityBankAccount } from "./LegalEntityBankAccounts";

const PROPERTY = "01920000-0000-7000-8000-00000000000a";
const ENTITY = "01920000-0000-7000-8000-00000000000b";
const ACCOUNT = "01920000-0000-7000-8000-00000000000c";
const DEPOSIT_ACCOUNT = "01920000-0000-7000-8000-00000000000d";

const legalEntities = [{ id: ENTITY, kind: "hoa", name: "WEG Musterstraße 1" }];

function accounts(): LegalEntityBankAccount[] {
  return [
    {
      id: ACCOUNT,
      legal_entity_id: ENTITY,
      kind: "hoa_fee",
      iban_masked: "DE89 **** **** **** **30 00",
      bic: null,
      bank_name: "Musterbank",
      holder: "WEG Musterstraße 1",
      is_default: false,
    },
    {
      id: DEPOSIT_ACCOUNT,
      legal_entity_id: ENTITY,
      kind: "deposit",
      iban_masked: "DE12 **** **** **** **99 00",
      bic: null,
      bank_name: "Musterbank",
      holder: "WEG Musterstraße 1",
      is_default: false,
    },
  ];
}

describe("LegalEntityBankAccounts", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the accounts, hides the button for deposit accounts and shows the deposit hint", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(accounts()));
    renderIntl(<LegalEntityBankAccounts propertyId={PROPERTY} legalEntities={legalEntities} canEdit />);
    await waitFor(() => expect(screen.getByText("DE89 **** **** **** **30 00")).toBeInTheDocument());
    expect(screen.getByText("Kautionskonto, kann nicht Standardkonto sein.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Als Standardkonto setzen" })).toHaveLength(1);
  });

  it("sets the default account via POST and reloads the list", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(accounts()))
      .mockResolvedValueOnce(jsonResponse({ ...accounts()[0], is_default: true }))
      .mockResolvedValueOnce(jsonResponse(accounts().map((a) => (a.id === ACCOUNT ? { ...a, is_default: true } : a))));
    renderIntl(<LegalEntityBankAccounts propertyId={PROPERTY} legalEntities={legalEntities} canEdit />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Als Standardkonto setzen" })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Als Standardkonto setzen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(`/api/bff/properties/${PROPERTY}/bank-accounts/${ACCOUNT}/default`);
    expect(init.method).toBe("POST");
    await waitFor(() => expect(screen.getAllByText("Standardkonto des Rechtsträgers")).toHaveLength(2));
  });

  it("hides the action without edit permission", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(accounts()));
    renderIntl(<LegalEntityBankAccounts propertyId={PROPERTY} legalEntities={legalEntities} canEdit={false} />);
    await waitFor(() => expect(screen.getByText("DE89 **** **** **** **30 00")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Als Standardkonto setzen" })).not.toBeInTheDocument();
  });
});
