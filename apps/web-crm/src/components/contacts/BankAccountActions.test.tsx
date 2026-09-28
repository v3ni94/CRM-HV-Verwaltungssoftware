import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { components } from "@mhvp/api-client";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankAccountActions, isEnded } from "./BankAccountActions";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh, back: vi.fn() }),
}));

type BankAccount = components["schemas"]["mhvp__contacts__schemas__BankAccountOut"];
type Change = components["schemas"]["BankAccountChangeOut"];

const CONTACT = "01920000-0000-7000-8000-00000000000a";
const ACCOUNT = "01920000-0000-7000-8000-00000000000b";
const CHANGE = "01920000-0000-7000-8000-00000000000d";
const CLERK = "01920000-0000-7000-8000-0000000000c1";
const APPROVER = "01920000-0000-7000-8000-0000000000c2";

function change(overrides: Partial<Change> = {}): Change {
  return {
    id: CHANGE,
    bank_account_id: ACCOUNT,
    kind: "end",
    valid_to: "2026-11-30",
    note: "Rückfrage am 28.09.2026",
    status: "pending",
    requested_by: CLERK,
    decided_by: null,
    decided_at: null,
    rejected_reason: null,
    created_at: "2026-09-28T10:00:00Z",
    ...overrides,
  };
}

function account(overrides: Partial<BankAccount> = {}): BankAccount {
  return {
    id: ACCOUNT,
    label: null,
    kind: null,
    is_default: false,
    bank_contact_id: null,
    iban_masked: "DE02 **** **** 2051",
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
    approval_status: "approved",
    requested_by: CLERK,
    decided_by: APPROVER,
    decided_at: "2026-09-01T10:00:00Z",
    rejected_reason: null,
    rejected_by: null,
    rejected_at: null,
    replaces_account_id: null,
    pending_change: null,
    ...overrides,
  };
}

function render(props: Partial<Parameters<typeof BankAccountActions>[0]> = {}) {
  const onReplace = vi.fn();
  renderIntl(
    <BankAccountActions
      contactId={CONTACT}
      account={account()}
      canEdit={true}
      canApprove={false}
      currentUserId={CLERK}
      onReplace={onReplace}
      {...props}
    />,
  );
  return onReplace;
}

describe("BankAccountActions", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    refresh.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("isEnded: rejected or valid_to in the past", () => {
    expect(isEnded(account(), "2026-09-28")).toBe(false);
    expect(isEnded(account({ valid_to: "2026-09-27" }), "2026-09-28")).toBe(true);
    expect(isEnded(account({ valid_to: "2026-09-28" }), "2026-09-28")).toBe(false);
    expect(isEnded(account({ approval_status: "rejected" }), "2026-09-28")).toBe(true);
  });

  it("offers change and end only with contacts:update on a released, open account", () => {
    const onReplace = render();
    expect(screen.getByRole("button", { name: "Beenden" })).toBeInTheDocument();
    userEvent.click(screen.getByRole("button", { name: "Ändern" }));
    return waitFor(() => expect(onReplace).toHaveBeenCalled());
  });

  it("hides the actions without the right, on pending accounts and on ended ones", () => {
    render({ canEdit: false });
    expect(screen.queryByRole("button", { name: "Beenden" })).not.toBeInTheDocument();
    render({ account: account({ approval_status: "pending" }) });
    expect(screen.queryByRole("button", { name: "Beenden" })).not.toBeInTheDocument();
    render({ account: account({ valid_to: "2020-01-01" }) });
    expect(screen.queryByRole("button", { name: "Beenden" })).not.toBeInTheDocument();
  });

  it("ends an account: posts valid_to and note, shows the pending notice for a clerk", async () => {
    fetchMock.mockResolvedValue(jsonResponse(account({ pending_change: change() })));
    render();
    await userEvent.click(screen.getByRole("button", { name: "Beenden" }));
    const form = screen.getByRole("form", { name: "Bankverbindung DE02 **** **** 2051 beenden" });
    expect(form).toBeInTheDocument();
    const date = screen.getByLabelText("Gültig bis");
    await userEvent.clear(date);
    await userEvent.type(date, "2026-11-30");
    await userEvent.type(screen.getByLabelText("Vermerk"), "Rückfrage am 28.09.2026");
    await userEvent.click(screen.getByRole("button", { name: "Beendigung speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/bff/contacts/${CONTACT}/bank-accounts/${ACCOUNT}/end`);
    expect(JSON.parse(String(init.body))).toEqual({ valid_to: "2026-11-30", note: "Rückfrage am 28.09.2026" });
    expect(await screen.findByRole("status")).toHaveTextContent("Beendigung zum 30.11.2026 gespeichert");
    expect(screen.getByText("Beendigung zum 30.11.2026 zur Freigabe")).toBeInTheDocument();
    expect(screen.getByText("selbst beantragt, Freigabe durch eine andere Person")).toBeInTheDocument();
    expect(refresh).toHaveBeenCalled();
  });

  it("shows the direct end for an approver on a normal contact", async () => {
    fetchMock.mockResolvedValue(jsonResponse(account({ valid_to: "2026-12-31" })));
    render({ canApprove: true, currentUserId: APPROVER });
    await userEvent.click(screen.getByRole("button", { name: "Beenden" }));
    await userEvent.click(screen.getByRole("button", { name: "Beendigung speichern" }));
    expect(await screen.findByRole("status")).toHaveTextContent("beendet zum 31.12.2026");
  });

  it("lets a second person with contacts:approve confirm a pending end, never the requester", async () => {
    fetchMock.mockResolvedValue(jsonResponse(account({ valid_to: "2026-11-30" })));
    render({ account: account({ pending_change: change() }), canApprove: true, currentUserId: APPROVER });
    expect(screen.getByText("Vermerk: Rückfrage am 28.09.2026")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Beenden" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Bestätigen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/bff/contacts/${CONTACT}/bank-accounts/${ACCOUNT}/changes/${CHANGE}/approve`);
    expect(await screen.findByRole("status")).toHaveTextContent("Beendigung bestätigt.");

    fetchMock.mockReset();
    render({ account: account({ pending_change: change() }), canApprove: true, currentUserId: CLERK });
    expect(screen.queryByRole("button", { name: "Bestätigen" })).not.toBeInTheDocument();
    expect(screen.getByText("selbst beantragt, Freigabe durch eine andere Person")).toBeInTheDocument();
  });

  it("rejects a pending end with a reason", async () => {
    fetchMock.mockResolvedValue(jsonResponse(account()));
    render({ account: account({ pending_change: change() }), canApprove: true, currentUserId: APPROVER });
    await userEvent.click(screen.getByRole("button", { name: "Ablehnen" }));
    await userEvent.type(screen.getByLabelText("Begründung der Ablehnung"), "Konto bleibt");
    await userEvent.click(screen.getByRole("button", { name: "Ablehnung bestätigen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/bff/contacts/${CONTACT}/bank-accounts/${ACCOUNT}/changes/${CHANGE}/reject`);
    expect(JSON.parse(String(init.body))).toEqual({ reason: "Konto bleibt" });
    expect(await screen.findByRole("status")).toHaveTextContent("Beendigung abgelehnt.");
  });
});
