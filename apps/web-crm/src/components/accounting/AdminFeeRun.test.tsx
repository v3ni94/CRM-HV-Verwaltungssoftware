import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AdminFeeRun } from "./AdminFeeRun";

const row = (status: string, extra: object = {}) => ({
  fee_setting_id: "f1", property_id: "p1", period_start: "2026-10-01", period_end: "2026-10-31",
  status, invoice_id: null, number: null, gross: "95.20", detail: null, ...extra,
});

describe("AdminFeeRun (Q02, Q15)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("previews first, then issues only after confirmation", async () => {
    const onIssued = vi.fn();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ confirmed: false, period_date: "2026-10-01", invoice_date: "2026-10-01", issued: 0, rows: [row("preview"), row("already_issued", { number: "PZ-1" })] }))
      .mockResolvedValueOnce(jsonResponse({ confirmed: true, period_date: "2026-10-01", invoice_date: "2026-10-01", issued: 1, rows: [row("issued", { number: "PZ-2" })] }));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<AdminFeeRun today="2026-10-01" propertyLabel={() => "P022 Honorarhaus"} onIssued={onIssued} />);
    expect(screen.queryByRole("button", { name: /ausstellen/ })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Vorschau" }));
    expect(await screen.findByText("Vorschau: 1 Rechnung(en) wären fällig.")).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toMatchObject({ confirm: false });
    await userEvent.click(screen.getByRole("button", { name: "1 Rechnung(en) ausstellen" }));
    await waitFor(() => expect(screen.getByText("1 Rechnung(en) ausgestellt.")).toBeInTheDocument());
    expect(confirm).toHaveBeenCalled();
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toMatchObject({ confirm: true });
    expect(onIssued).toHaveBeenCalled();
  });

  it("does not issue when the confirmation is declined and shows API errors", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ confirmed: false, period_date: "2026-10-01", invoice_date: "2026-10-01", issued: 0, rows: [row("preview")] }));
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderIntl(<AdminFeeRun today="2026-10-01" propertyLabel={() => "P"} />);
    await userEvent.click(screen.getByRole("button", { name: "Vorschau" }));
    await userEvent.click(await screen.findByRole("button", { name: "1 Rechnung(en) ausstellen" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fetchMock.mockResolvedValueOnce(jsonResponse({ title: "Gesperrt", status: 409 }, 409));
    await userEvent.click(screen.getByRole("button", { name: "Vorschau" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
