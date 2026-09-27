import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { SettlementProposalPanel } from "./SettlementProposalPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const LEDGER = "0192abcd-0000-7000-8000-000000000001";
const OI1 = "0192abcd-0000-7000-8000-000000000011";
const OI2 = "0192abcd-0000-7000-8000-000000000012";

const proposal = {
  rule: "M10-03",
  rule_version: "1",
  note: "Vorschlag nach gesetzlicher Reihenfolge, Rechtsprüfung vor G1 offen",
  requires_confirmation: true,
  basis: "statutory_order",
  amount: "500.00",
  as_of: "2026-09-26",
  allocations: [
    { open_item_id: OI1, amount: "300.00", remaining_before: "300.00", reason: "gesetzliche Reihenfolge", rank: 1, due_date: "2026-08-01", claim_class: "principal" },
    { open_item_id: OI2, amount: "195.00", remaining_before: "250.00", reason: "gesetzliche Reihenfolge", rank: 2, due_date: "2026-09-01", claim_class: "principal" },
  ],
  unallocated: "5.00",
  fingerprint: "f".repeat(64),
};

function panel() {
  return (
    <SettlementProposalPanel
      ledgerId={LEDGER}
      debtors={[{ id: "d1", number: "090001", name: "Eigentümer" }]}
      bankAccounts={[{ id: "b1", number: "001200", name: "Bank" }]}
      today="2026-09-26"
    />
  );
}

describe("SettlementProposalPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the proposal with the legal review note and confirms it as a draft with the fingerprint", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(proposal))
      .mockResolvedValueOnce(jsonResponse({ id: "entry-1", status: "draft" }, 201));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(panel());
    await userEvent.type(screen.getByLabelText("Zahlbetrag"), "500.00");
    await userEvent.click(screen.getByText("Vorschlag berechnen"));
    await screen.findByTestId("settlement-proposal");
    expect(screen.getByText("Vorschlag nach gesetzlicher Reihenfolge, Rechtsprüfung vor G1 offen")).toBeInTheDocument();
    expect(screen.getAllByText("gesetzliche Reihenfolge").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByTestId("settlement-unallocated").textContent).toMatch(/5,00/);
    const first = fetchMock.mock.calls[0]!;
    expect(String(first[0])).toBe(`/api/bff/accounting/ledgers/${LEDGER}/open-items/settlement-proposal`);
    expect(JSON.parse(String((first[1] as RequestInit).body))).toEqual({ account_id: "d1", amount: "500.00", as_of: "2026-09-26", purpose: null });

    await userEvent.click(screen.getByText("Vorschlag bestätigen (Entwurf anlegen)"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const second = fetchMock.mock.calls[1]!;
    expect(String(second[0])).toBe(`/api/bff/accounting/ledgers/${LEDGER}/open-items/settlement-proposal/confirm`);
    const body = JSON.parse(String((second[1] as RequestInit).body));
    expect(body.fingerprint).toBe("f".repeat(64));
    expect(body.bank_account_id).toBe("b1");
    expect(body.post_immediately).toBeUndefined();
    expect(screen.getByText(/Entwurf angelegt/)).toBeInTheDocument();
  });

  it("does not confirm when the staff member cancels the question", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(proposal));
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderIntl(panel());
    await userEvent.type(screen.getByLabelText("Zahlbetrag"), "500.00");
    await userEvent.click(screen.getByText("Vorschlag berechnen"));
    await screen.findByTestId("settlement-proposal");
    await userEvent.click(screen.getByText("Vorschlag bestätigen (Entwurf anlegen)"));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows the problem message when the proposal is stale", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(proposal))
      .mockResolvedValueOnce(jsonResponse({ code: "MHVP-CORE-0004", detail: "Der Vorschlag ist nicht mehr aktuell." }, 409));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(panel());
    await userEvent.type(screen.getByLabelText("Zahlbetrag"), "500.00");
    await userEvent.click(screen.getByText("Vorschlag berechnen"));
    await screen.findByTestId("settlement-proposal");
    await userEvent.click(screen.getByText("Vorschlag bestätigen (Entwurf anlegen)"));
    expect(await screen.findByRole("alert")).toHaveTextContent(/nicht mehr aktuell/);
  });
});
