import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CreditorsPanel } from "./CreditorsPanel";
import { RecurringPlansPanel } from "./RecurringPlansPanel";

const PLAN = "0192abcd-0000-7000-8000-000000000081";
const plan = (auto_post: boolean) => ({
  id: PLAN, text: "Wartung", gross: "119.00", vat_percent: "19.00", interval_months: 1, start_date: "2026-01-31",
  end_date: null, next_due: "2026-03-31", ended_at: null, order_reference: null, anchor_day: 31, service_contract_id: null, auto_post,
});

describe("GA03-07 plan flag", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the flag and requests it with PATCH", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(async () => jsonResponse([plan(false)]))
      .mockImplementationOnce(async () => jsonResponse(plan(true)))
      .mockImplementationOnce(async () => jsonResponse([plan(true)]));
    renderIntl(<RecurringPlansPanel ledgers={[{ id: "l1", label: "WEG" }]} />);
    expect(await screen.findByTestId("plan-auto-post")).toHaveTextContent("nein");
    await userEvent.click(screen.getByRole("button", { name: "Anfordern" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Kennzeichen gespeichert."));
    expect(fetchMock.mock.calls[1]?.[0]).toBe(`/api/bff/accounting/recurring-invoices/${PLAN}`);
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({ auto_post: true });
    expect(await screen.findByText("ja")).toBeInTheDocument();
  });

  it("reports the lock state after a run", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(async () => jsonResponse([plan(true)]))
      .mockImplementationOnce(async () => jsonResponse({ id: "i1", auto_post_requested: true, auto_post_state: "locked_g1" }, 201))
      .mockImplementationOnce(async () => jsonResponse([plan(true)]));
    renderIntl(<RecurringPlansPanel ledgers={[{ id: "l1", label: "WEG" }]} />);
    await userEvent.click(await screen.findByRole("button", { name: "Entwurf erzeugen" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Freigabestufe G1 geschlossen");
  });

  it("shows the default bank rule hint in the creditor view", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementationOnce(async () => jsonResponse([]));
    renderIntl(<CreditorsPanel ledgers={[{ id: "l1", label: "WEG" }]} />);
    expect(await screen.findByTestId("creditor-default-rule-hint")).toHaveTextContent("Vorschlagsregel");
  });
});
