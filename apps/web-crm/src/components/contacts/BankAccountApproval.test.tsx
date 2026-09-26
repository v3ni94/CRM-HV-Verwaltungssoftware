import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { components } from "@mhvp/api-client";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankAccountApproval } from "./BankAccountApproval";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh, back: vi.fn() }) }));

type BankAccount = components["schemas"]["mhvp__contacts__schemas__BankAccountOut"];

const CONTACT = "01920000-0000-7000-8000-00000000000a";
const ACCOUNT = "01920000-0000-7000-8000-00000000000b";
const CLERK = "01920000-0000-7000-8000-0000000000c1";
const APPROVER = "01920000-0000-7000-8000-0000000000c2";

function account(overrides: Partial<BankAccount> = {}): BankAccount {
  return {
    id: ACCOUNT,
    label: null,
    iban_masked: "DE89 **** **** **** **30 00",
    bic: null,
    bank_name: null,
    holder: null,
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
    approval_status: "pending",
    requested_by: CLERK,
    decided_by: null,
    decided_at: null,
    ...overrides,
  };
}

describe("BankAccountApproval", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    refresh.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("lets a second person with contacts:approve release a pending IBAN", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(account({ approval_status: "approved" })));
    renderIntl(<BankAccountApproval contactId={CONTACT} account={account()} canApprove currentUserId={APPROVER} />);
    expect(screen.getByText("zur Freigabe")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Freigeben" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(`/contacts/${CONTACT}/bank-accounts/${ACCOUNT}/approve`);
  });

  it("hides the buttons for the requester and shows the four eyes hint", () => {
    renderIntl(<BankAccountApproval contactId={CONTACT} account={account()} canApprove currentUserId={CLERK} />);
    expect(screen.queryByRole("button", { name: "Freigeben" })).not.toBeInTheDocument();
    expect(screen.getByText(/Freigabe durch eine andere Person/)).toBeInTheDocument();
  });

  it("hides the buttons without permission and for decided accounts", () => {
    const { unmount } = renderIntl(
      <BankAccountApproval contactId={CONTACT} account={account()} canApprove={false} currentUserId={APPROVER} />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    unmount();
    renderIntl(
      <BankAccountApproval
        contactId={CONTACT}
        account={account({ approval_status: "approved" })}
        canApprove
        currentUserId={APPROVER}
      />,
    );
    expect(screen.getByText("freigegeben")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
