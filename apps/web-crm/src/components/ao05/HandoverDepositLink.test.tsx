import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HandoverDepositLink } from "./HandoverDepositLink";

const state = {
  protocol_id: "p",
  contract_id: "c",
  deposit_id: "d",
  deposit_status: "held",
  deposit_amount_due: "1500.00",
  protocol_deposit_amount: "1200.00",
  difference: "-300.00",
  iban_suffix: "4321",
  contact_id: null,
  bank_account_id: null,
  bank_account_approval: null,
  hints: ["Kaution weicht ab"],
};

describe("HandoverDepositLink (AN19-CRM)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the comparison and the four eyes hint, then links the account", async () => {
    const f = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(state))
      .mockResolvedValueOnce(jsonResponse({ ...state, bank_account_approval: "pending" }));
    renderIntl(<HandoverDepositLink base="/api/bff/handover/protocols/p1" disabled={false} />);
    expect(screen.getByText(/Vier-Augen-Prinzip/)).toBeInTheDocument();
    expect(await screen.findByTestId("deposit-hints")).toHaveTextContent("Kaution weicht ab");
    await userEvent.click(screen.getByRole("button", { name: "Konto zur Freigabe übergeben" }));
    expect(await screen.findByText("Das Konto wurde zur Freigabe übergeben.")).toBeInTheDocument();
    expect(f.mock.calls[1]![0]).toBe("/api/bff/handover/protocols/p1/deposit/link");
    expect((f.mock.calls[1]![1] as RequestInit).method).toBe("POST");
  });

  it("disables linking for a locked protocol and shows errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Gesperrt", status: 403 }, 403));
    renderIntl(<HandoverDepositLink base="/api/bff/handover/protocols/p1" disabled />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Konto zur Freigabe übergeben" })).toBeDisabled();
  });
});
