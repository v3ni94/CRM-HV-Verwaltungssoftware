import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AccountsManager, type ManagedAccount } from "./AccountsManager";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const account: ManagedAccount = {
  id: "0192abcd-0000-7000-8000-00000000c001",
  number: "6000",
  name: "Gebäudeversicherung",
  category: "cost",
  statement_kind: "reserve",
  type: "expense",
  vat_option: "none",
  relevant_for_cash_report: false,
  visible: true,
  active: true,
  is_system: false,
};

describe("AccountsManager (SA-08)", () => {
  it("zeigt Art der Abrechnung und Mehrschlüsselverteilung", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        ledger_account_id: account.id,
        items: [
          { allocation_key_id: "k1", code: "MEA", name: "Miteigentumsanteile", share_percent: "60.0000" },
          { allocation_key_id: "k2", code: "QM", name: "Wohnfläche", share_percent: "40.0000" },
        ],
        total_percent: "100.0000",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<AccountsManager ledgerId="l1" accounts={[account]} canCreate={false} canUpdate={false} />);
    expect(screen.getByText("Rücklage", { selector: "span" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Verteilung" }));
    await waitFor(() => expect(screen.getByText(/MEA Miteigentumsanteile: 60.0000 %/)).toBeInTheDocument());
    expect(screen.getByText("Summe 100.0000 %")).toBeInTheDocument();
  });
});
