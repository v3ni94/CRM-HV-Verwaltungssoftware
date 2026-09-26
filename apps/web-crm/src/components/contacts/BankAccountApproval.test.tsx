import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { components } from "@mhvp/api-client";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankAccountApproval } from "./BankAccountApproval";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh, back: vi.fn() }),
}));

type BankAccount =
  components["schemas"]["mhvp__contacts__schemas__BankAccountOut"];

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
    fetchMock.mockResolvedValueOnce(
      jsonResponse(account({ approval_status: "approved" })),
    );
    renderIntl(
      <BankAccountApproval
        contactId={CONTACT}
        account={account()}
        canApprove
        currentUserId={APPROVER}
      />,
    );
    expect(screen.getByText("zur Freigabe")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Freigeben" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      `/contacts/${CONTACT}/bank-accounts/${ACCOUNT}/approve`,
    );
  });

  it("rejects only with a reason and sends it to the API", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        account({
          approval_status: "rejected",
          decided_at: "2026-09-26T09:00:00Z",
        }),
      ),
    );
    renderIntl(
      <BankAccountApproval
        contactId={CONTACT}
        account={account()}
        canApprove
        currentUserId={APPROVER}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Ablehnen" }));
    const submit = screen.getByRole("button", { name: "Ablehnung bestätigen" });
    expect(submit).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.type(
      screen.getByLabelText("Begründung der Ablehnung"),
      "IBAN nicht belegt",
    );
    await userEvent.click(submit);
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("abgelehnt."),
    );
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      `/bank-accounts/${ACCOUNT}/reject`,
    );
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      reason: "IBAN nicht belegt",
    });
    expect(screen.getByText("abgelehnt")).toBeInTheDocument();
    expect(screen.getByText(/^am \d{2}\.\d{2}\.\d{4}/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("cancelling the reject form keeps the account pending and sends nothing", async () => {
    renderIntl(
      <BankAccountApproval
        contactId={CONTACT}
        account={account()}
        canApprove
        currentUserId={APPROVER}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Ablehnen" }));
    await userEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(
      screen.getByRole("button", { name: "Freigeben" }),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the API problem detail when the release is refused", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          title: "Vier-Augen-Prinzip",
          status: 409,
          detail: "Die Freigabe muss eine andere Person vornehmen.",
        },
        409,
      ),
    );
    renderIntl(
      <BankAccountApproval
        contactId={CONTACT}
        account={account()}
        canApprove
        currentUserId={APPROVER}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Freigeben" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("andere Person"),
    );
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.getByText("zur Freigabe")).toBeInTheDocument();
  });

  it("hides the buttons for a platform admin and explains it", () => {
    renderIntl(
      <BankAccountApproval
        contactId={CONTACT}
        account={account()}
        canApprove
        currentUserId={APPROVER}
        isPlatformAdmin
      />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/Plattformadministratoren/)).toBeInTheDocument();
  });

  it("hides the buttons for the requester and shows the four eyes hint", () => {
    renderIntl(
      <BankAccountApproval
        contactId={CONTACT}
        account={account()}
        canApprove
        currentUserId={CLERK}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "Freigeben" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Freigabe durch eine andere Person/),
    ).toBeInTheDocument();
  });

  it("hides the buttons without permission and for decided accounts", () => {
    const { unmount } = renderIntl(
      <BankAccountApproval
        contactId={CONTACT}
        account={account()}
        canApprove={false}
        currentUserId={APPROVER}
      />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/contacts:approve/)).toBeInTheDocument();
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
