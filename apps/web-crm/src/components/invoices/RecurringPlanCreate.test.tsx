import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { RecurringPlanCreate } from "./RecurringPlanCreate";

describe("RecurringPlanCreate (Q02)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("stays disabled until valid and posts the plan", async () => {
    const onCreated = vi.fn();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(async () => jsonResponse([{ id: "a1", number: "043000", name: "Allgemeinstrom" }]))
      .mockImplementationOnce(async () => jsonResponse({ items: [{ id: "p1", display_name: "Stadtwerke" }], total: 1, page: 1, page_size: 50 }))
      .mockImplementationOnce(async () => jsonResponse({ id: "plan1", next_due: "2026-11-01" }, 201));
    renderIntl(<RecurringPlanCreate ledger="l1" onCreated={onCreated} />);
    const submit = screen.getByRole("button", { name: "Rechnungsplan anlegen" });
    expect(submit).toBeDisabled();
    await userEvent.click(screen.getByText("Neuen Rechnungsplan anlegen"));
    await userEvent.type(screen.getByLabelText("Aussteller suchen"), "Stadt");
    await userEvent.click(screen.getByRole("button", { name: "Suchen" }));
    await userEvent.selectOptions(await screen.findByLabelText("Aussteller"), "p1");
    await userEvent.selectOptions(await screen.findByLabelText("Kostenkonto"), "a1");
    await userEvent.type(screen.getByLabelText("Leistung"), "Allgemeinstrom");
    await userEvent.type(screen.getByLabelText("Brutto je Rechnung"), "119,00");
    await userEvent.type(screen.getByLabelText("Erste Fälligkeit"), "2026-11-01");
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    const call = fetchMock.mock.calls[2];
    expect(call?.[0]).toBe("/api/bff/accounting/recurring-invoices");
    expect(JSON.parse(call?.[1]?.body as string)).toMatchObject({
      ledger_id: "l1", provider_contact_id: "p1", account_id: "a1", gross: "119.00", vat_percent: "19", interval_months: 1, start_date: "2026-11-01", end_date: null,
    });
  }, 20000);

  it("rejects an end date before the start", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    renderIntl(<RecurringPlanCreate ledger="l1" onCreated={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Erste Fälligkeit"), "2026-11-01");
    await userEvent.type(screen.getByLabelText("Enddatum (optional)"), "2026-10-01");
    expect(screen.getByRole("button", { name: "Rechnungsplan anlegen" })).toBeDisabled();
  });
});
