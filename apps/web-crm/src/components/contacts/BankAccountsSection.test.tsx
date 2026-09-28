import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { components } from "@mhvp/api-client";

import { renderIntl } from "@/test/intl";

import { BankAccountsSection } from "./BankAccountsSection";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), back: vi.fn() }),
}));

type BankAccount = components["schemas"]["mhvp__contacts__schemas__BankAccountOut"];

const CONTACT = "01920000-0000-7000-8000-00000000000a";
const OLD = "01920000-0000-7000-8000-00000000000b";
const NEW = "01920000-0000-7000-8000-00000000000c";
const CLERK = "01920000-0000-7000-8000-0000000000c1";

function account(overrides: Partial<BankAccount> = {}): BankAccount {
  return {
    id: OLD,
    label: null,
    kind: "rent",
    is_default: true,
    bank_contact_id: null,
    iban_masked: "DE02 **** **** 2051",
    bic: "BYLADEM1001",
    bank_name: "DKB",
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
    requested_by: CLERK,
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

describe("BankAccountsSection", () => {
  it("shows the empty state and the add button only with contacts:update", () => {
    renderIntl(<BankAccountsSection contactId={CONTACT} accounts={[]} canEdit={false} canApprove={false} currentUserId={CLERK} />);
    expect(screen.getByText("Keine Einträge.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bankverbindung hinzufügen" })).not.toBeInTheDocument();
  });

  it("lists accounts with the replaced version and opens the add form", async () => {
    const accounts = [
      account({ valid_to: "2026-09-30", is_default: false }),
      account({ id: NEW, iban_masked: "DE02 **** **** 5030", valid_from: "2026-10-01", replaces_account_id: OLD, is_default: true }),
    ];
    renderIntl(<BankAccountsSection contactId={CONTACT} accounts={accounts} canEdit={true} canApprove={false} currentUserId={CLERK} />);
    // Cards (phone) and table (desktop) both render the rows.
    expect(screen.getAllByText("DE02 **** **** 5030")).toHaveLength(2);
    expect(screen.getAllByText("ersetzt DE02 **** **** 2051")).toHaveLength(2);
    expect(screen.getAllByText("30.09.2026").length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "Bankverbindung hinzufügen" }));
    expect(screen.getByRole("form", { name: "Neue Bankverbindung" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bankverbindung hinzufügen" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it("opens the replace form for an account from its actions", async () => {
    renderIntl(<BankAccountsSection contactId={CONTACT} accounts={[account()]} canEdit={true} canApprove={false} currentUserId={CLERK} />);
    await userEvent.click(screen.getAllByRole("button", { name: "Ändern" })[0]!);
    expect(screen.getByRole("form", { name: "Neue IBAN für DE02 **** **** 2051" })).toBeInTheDocument();
  });
});
