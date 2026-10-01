import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankLimitsCard } from "./BankLimitsCard";

vi.mock("./BankAccountSelect", () => ({
  BankAccountSelect: ({ onChange }: { onChange: (a: { id: string } | null) => void }) => (
    <button type="button" onClick={() => onChange({ id: "acc1" })}>
      Konto wählen
    </button>
  ),
}));

const LIMITS = {
  property_bank_account_id: "acc1",
  single_order_limit: "5000.00",
  daily_limit: null,
  source_status: "zu verifizieren",
  verification_of_payee: "Empfängerprüfung ist eine bankseitige Prüfung.",
  lead_times: { frst_days: 5, rcur_days: null, pre_notification_days: 14, note: "Fristen sind Betreibereingaben." },
};

describe("BankLimitsCard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads limits for the chosen account, shows the payee check note and saves", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) =>
      jsonResponse(init?.method === "PUT" ? { ...LIMITS, daily_limit: "20000.00" } : LIMITS),
    );
    renderIntl(<BankLimitsCard />);
    await userEvent.click(screen.getByRole("button", { name: "Konto wählen" }));
    expect(await screen.findByTestId("vop-note")).toHaveTextContent("Empfängerprüfung");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/accounting/payment-runs/bank-limits/acc1");
    const daily = screen.getByLabelText("Tageslimit in EUR");
    await userEvent.type(daily, "20000,00");
    await userEvent.click(screen.getByRole("button", { name: "Limits speichern" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Limits gespeichert."));
    const put = fetchMock.mock.calls.find(([, i]) => i?.method === "PUT");
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({
      single_order_limit: "5000.00",
      daily_limit: "20000.00",
      dd_lead_days_frst: 5,
      dd_lead_days_rcur: null,
      pre_notification_days: 14,
    });
  });

  it("blocks saving an invalid amount", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(LIMITS));
    renderIntl(<BankLimitsCard />);
    await userEvent.click(screen.getByRole("button", { name: "Konto wählen" }));
    const daily = await screen.findByLabelText("Tageslimit in EUR");
    await userEvent.type(daily, "abc");
    expect(screen.getByRole("button", { name: "Limits speichern" })).toBeDisabled();
  });
});
