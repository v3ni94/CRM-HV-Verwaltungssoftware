import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CreditorsPanel } from "./CreditorsPanel";
import { RecurringPlansPanel } from "./RecurringPlansPanel";

const ACC = "0192abcd-0000-7000-8000-000000000070";
const PLAN = "0192abcd-0000-7000-8000-000000000071";

describe("CreditorsPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists creditors with balance and opens the statement", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(async () =>
        jsonResponse([{ account_id: ACC, number: "070000", name: "Hausmeister GmbH", balance: "1190.00", open_items: 1, open_amount: "1190.00", invoices: 1 }]),
      )
      .mockImplementationOnce(async () =>
        jsonResponse({
          opening_balance: "0.00",
          closing_balance: "-1190.00",
          movements: [{ entry_id: "e1", number: "2026-1", booking_date: "2026-02-01", text: "Rechnung R-1", debit: "0.00", credit: "1190.00", balance: "-1190.00" }],
        }),
      );
    renderIntl(<CreditorsPanel ledgers={[{ id: "l1", label: "WEG" }]} />);
    expect(await screen.findByText("Hausmeister GmbH")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/accounting/ledgers/l1/creditors");
    await userEvent.click(screen.getByText("070000"));
    const statement = await screen.findByTestId("creditor-statement");
    expect(statement).toHaveTextContent("Kontoauszug 070000 Hausmeister GmbH");
    expect(statement).toHaveTextContent("Rechnung R-1");
    expect(fetchMock.mock.calls[1]?.[0]).toBe(`/api/bff/accounting/ledgers/l1/creditors/${ACC}/statement`);
  });
});

describe("RecurringPlansPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("ends a plan with date and reason", async () => {
    const plan = { id: PLAN, text: "Wartung", gross: "119.00", vat_percent: "19", interval_months: 1, start_date: "2026-01-31", end_date: null, next_due: "2026-03-31", ended_at: null, order_reference: "V-7" };
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(async () => jsonResponse([plan]))
      .mockImplementationOnce(async () => jsonResponse({ ...plan, ended_at: "2026-03-01" }))
      .mockImplementationOnce(async () => jsonResponse([{ ...plan, ended_at: "2026-03-01" }]));
    renderIntl(<RecurringPlansPanel ledgers={[{ id: "l1", label: "WEG" }]} />);
    expect(await screen.findByText("Wartung")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Beenden"));
    const confirm = screen.getByText("Plan beenden");
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Beendet zum"), "2026-03-01");
    await userEvent.type(screen.getByLabelText("Grund"), "Vertrag gekündigt");
    await userEvent.click(confirm);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Rechnungsplan beendet."));
    expect(fetchMock.mock.calls[1]?.[0]).toBe(`/api/bff/accounting/recurring-invoices/${PLAN}/end`);
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({ ended_at: "2026-03-01", reason: "Vertrag gekündigt" });
    expect(await screen.findByText("beendet zum 01.03.2026")).toBeInTheDocument();
  });
});
