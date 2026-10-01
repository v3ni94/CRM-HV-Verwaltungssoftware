import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AdminFeePanel } from "./AdminFeePanel";

const ACC = "0192abcd-0000-7000-8000-00000000c001";
const FEE = "0192abcd-0000-7000-8000-00000000f101";
const fee = {
  id: FEE,
  property_id: "p1",
  start_date: "2026-01-01",
  end_date: null,
  interval: "monthly",
  vat_percent: "19",
  amounts_per_unit_type: { apartment: "40.00" },
  invoice_count: 0,
  termination_date: "2026-12-31",
  due_day_rule: "day",
  due_day: 15,
  sev_fee_amount: "25.50",
};

function load(fetchMock: ReturnType<typeof vi.spyOn>, fees: unknown[]) {
  fetchMock
    .mockResolvedValueOnce(jsonResponse(fees))
    .mockResolvedValueOnce(jsonResponse({ rows: [] }))
    .mockResolvedValueOnce(jsonResponse([]));
}

describe("AdminFeePanel GA03-06 fields", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows termination, due rule and SEV amount in the fee list", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    load(fetchMock, [fee]);
    renderIntl(<AdminFeePanel properties={[{ id: "p1", label: "P022 Haus" }]} today="2026-02-15" />);
    expect(await screen.findByText("Kündigung zum 31.12.2026")).toBeInTheDocument();
    expect(screen.getByText("Fester Tag im Monat (15)")).toBeInTheDocument();
    expect(screen.getByText("SE-Einheit: 25,50 EUR")).toBeInTheDocument();
  });

  it("sends the new fields on create and blocks invalid input", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    load(fetchMock, []);
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: FEE }, 201));
    load(fetchMock, [fee]);
    renderIntl(<AdminFeePanel properties={[{ id: "p1", label: "P022 Haus" }]} today="2026-02-15" />);
    const create = await screen.findByRole("button", { name: "Einrichten" });
    await userEvent.selectOptions(screen.getByLabelText("Fälligkeitsregel"), "day");
    await userEvent.type(screen.getByLabelText("Tag (1 bis 31)"), "40");
    expect(create).toBeDisabled();
    await userEvent.clear(screen.getByLabelText("Tag (1 bis 31)"));
    await userEvent.type(screen.getByLabelText("Tag (1 bis 31)"), "15");
    await userEvent.type(screen.getByLabelText("Erlöskonto (ID, optional)"), "kein-uuid");
    expect(create).toBeDisabled();
    await userEvent.clear(screen.getByLabelText("Erlöskonto (ID, optional)"));
    await userEvent.type(screen.getByLabelText("Erlöskonto (ID, optional)"), ACC);
    await userEvent.type(screen.getByLabelText("Honorar je SE-Einheit netto (optional)"), "25,50");
    await userEvent.type(screen.getByLabelText("Kündigungsdatum (optional)"), "2026-12-31");
    await userEvent.type(screen.getByLabelText("Je Wohnung (netto)"), "40.00");
    await userEvent.click(create);
    await waitFor(() => expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/bff/accounting/admin-fees"));
    expect(JSON.parse(fetchMock.mock.calls[3]?.[1]?.body as string)).toMatchObject({
      property_id: "p1",
      termination_date: "2026-12-31",
      due_day_rule: "day",
      due_day: 15,
      account_id: ACC,
      sev_fee_amount: "25.50",
      amounts_per_unit_type: { apartment: "40.00" },
    });
  });
});
