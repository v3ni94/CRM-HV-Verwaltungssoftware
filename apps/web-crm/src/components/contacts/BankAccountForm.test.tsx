import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { components } from "@mhvp/api-client";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankAccountForm } from "./BankAccountForm";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh, back: vi.fn() }),
}));

type BankAccount = components["schemas"]["mhvp__contacts__schemas__BankAccountOut"];

const CONTACT = "01920000-0000-7000-8000-00000000000a";
const OLD = "01920000-0000-7000-8000-00000000000b";

function account(overrides: Partial<BankAccount> = {}): BankAccount {
  return {
    id: OLD,
    label: "Mietkonto",
    kind: "rent",
    is_default: true,
    bank_contact_id: null,
    iban_masked: "DE02 **** **** 2051",
    bic: "BYLADEM1001",
    bank_name: "Deutsche Kreditbank",
    holder: "Karl Konto",
    valid_from: "2026-01-01",
    valid_to: null,
    sepa_enabled: false,
    mandate_reference: null,
    mandate_signed_on: null,
    mandate_granted_via: null,
    mandate_note: null,
    mandate_document_id: null,
    mandate_scheme: "core",
    mandate_status: "active",
    mandate_revoked_on: null,
    approval_status: "approved",
    requested_by: null,
    decided_by: null,
    decided_at: null,
    rejected_reason: null,
    rejected_by: null,
    rejected_at: null,
    replaces_account_id: null,
    pending_change: null,
    ...overrides,
  };
}

describe("BankAccountForm", () => {
  const fetchMock = vi.fn<typeof fetch>();
  const onClose = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    refresh.mockReset();
    onClose.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("refuses an IBAN with a wrong check digit without calling the API", async () => {
    renderIntl(<BankAccountForm contactId={CONTACT} mode="add" onClose={onClose} />);
    await userEvent.type(screen.getByLabelText("IBAN"), "DE02120300000000202052");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText(/IBAN ist ungültig/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("adds an account: posts the normalised IBAN and shows the pending notice", async () => {
    fetchMock.mockResolvedValue(jsonResponse(account({ approval_status: "pending" }), 201));
    renderIntl(<BankAccountForm contactId={CONTACT} mode="add" onClose={onClose} />);
    await userEvent.type(screen.getByLabelText("IBAN"), "de02 1203 0000 0000 2020 51");
    await userEvent.type(screen.getByLabelText("BIC"), "byladem1001");
    await userEvent.type(screen.getByLabelText("Kontoinhaber"), "Karl Konto");
    await userEvent.click(screen.getByLabelText("Standardkonto"));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/bff/contacts/${CONTACT}/bank-accounts`);
    expect(init.method).toBe("POST");
    const body = JSON.parse(String(init.body));
    expect(body.iban).toBe("DE02120300000000202051");
    expect(body.bic).toBe("BYLADEM1001");
    expect(body.holder).toBe("Karl Konto");
    expect(body.is_default).toBe(true);
    expect(body.valid_to).toBeNull();
    expect(await screen.findByRole("status")).toHaveTextContent("Status zur Freigabe");
    expect(refresh).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Schließen" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("changes an account as a new version via the replace path, default handed over later", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(account({ id: "01920000-0000-7000-8000-00000000000c", approval_status: "pending", replaces_account_id: OLD }), 201),
    );
    renderIntl(<BankAccountForm contactId={CONTACT} mode="replace" account={account()} onClose={onClose} />);
    expect(screen.getByRole("form", { name: "Neue IBAN für DE02 **** **** 2051" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Standardkonto")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Kontoinhaber")).toHaveValue("Karl Konto");
    await userEvent.type(screen.getByLabelText("IBAN"), "DE02500105170137075030");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/bff/contacts/${CONTACT}/bank-accounts/${OLD}/replace`);
    const body = JSON.parse(String(init.body));
    expect(body.iban).toBe("DE02500105170137075030");
    expect(body.is_default).toBe(false);
    expect(body.holder).toBe("Karl Konto");
  });

  it("shows the API problem message", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ title: "Diese IBAN ist beim Kontakt bereits hinterlegt", status: 409, code: "MHVP-CONT-0003" }, 409),
    );
    renderIntl(<BankAccountForm contactId={CONTACT} mode="add" onClose={onClose} />);
    await userEvent.type(screen.getByLabelText("IBAN"), "DE02120300000000202051");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("bereits hinterlegt");
  });
});
