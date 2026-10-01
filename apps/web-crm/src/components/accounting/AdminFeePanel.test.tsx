import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AdminFeePanel } from "./AdminFeePanel";

const FEE = "0192abcd-0000-7000-8000-00000000f001";
const INV = "0192abcd-0000-7000-8000-00000000a001";
const fee = {
  id: FEE,
  property_id: "p1",
  start_date: "2026-01-01",
  end_date: null,
  interval: "quarterly",
  vat_percent: "19",
  amounts_per_unit_type: { apartment: "40.00" },
  invoice_count: 0,
};
const period = (status: "due" | "issued") => ({
  fee_setting_id: FEE,
  period_start: "2026-01-01",
  period_end: "2026-03-31",
  status,
  number: status === "issued" ? "PZ-2026-000001" : null,
  draft: { net: "80.00", vat: "15.20", gross: "95.20" },
});
const invoice = {
  id: INV,
  number: "PZ-2026-000001",
  kind: "invoice",
  invoice_date: "2026-04-02",
  period_start: "2026-01-01",
  period_end: "2026-03-31",
  status: "issued",
  gross: "95.20",
  cancelled_at: null,
  xrechnung_url: `/api/v1/accounting/invoices/${INV}/xrechnung.xml`,
};

function mockLoad(fetchMock: ReturnType<typeof vi.spyOn>, rows: unknown[], invoices: unknown[]) {
  fetchMock
    .mockResolvedValueOnce(jsonResponse([fee]))
    .mockResolvedValueOnce(jsonResponse({ period_date: "2026-02-15", rows }))
    .mockResolvedValueOnce(jsonResponse(invoices));
}

describe("AdminFeePanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists fees and due periods and issues a period after confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    mockLoad(fetchMock, [period("due")], []);
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: INV, number: "PZ-2026-000001" }));
    mockLoad(fetchMock, [period("issued")], [invoice]);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<AdminFeePanel properties={[{ id: "p1", label: "P022 Honorarhaus" }]} today="2026-02-15" />);
    expect(await screen.findByText("95,20 EUR")).toBeInTheDocument();
    expect(screen.getAllByText("vierteljährlich").length).toBeGreaterThan(1);
    await userEvent.click(screen.getByRole("button", { name: "Ausstellen" }));
    await waitFor(() => expect(screen.getByText("Rechnung ausgestellt.")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[3]?.[0])).toContain(`/admin-fees/${FEE}/invoice-issue?period_start=2026-01-01`);
    expect(await screen.findByText("ausgestellt (PZ-2026-000001)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "XRechnung" })).toHaveAttribute(
      "href",
      `/api/bff/accounting/invoices/${INV}/xrechnung.xml`,
    );
  });

  it("does not issue without confirmation and cancels only with a reason", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    mockLoad(fetchMock, [period("due")], [invoice]);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const prompt = vi.spyOn(window, "prompt").mockReturnValueOnce(null).mockReturnValueOnce("Einheiten korrigiert");
    fetchMock.mockResolvedValueOnce(jsonResponse({ ...invoice, id: "c", kind: "credit_note", gross: "-95.20" }, 201));
    mockLoad(fetchMock, [period("due")], []);
    renderIntl(<AdminFeePanel properties={[]} today="2026-02-15" />);
    await userEvent.click(await screen.findByRole("button", { name: "Ausstellen" }));
    await userEvent.click(screen.getByRole("button", { name: "Stornieren" }));
    expect(fetchMock).toHaveBeenCalledTimes(3);
    await userEvent.click(screen.getByRole("button", { name: "Stornieren" }));
    await waitFor(() => expect(screen.getByText("Gutschrift erstellt, Rechnung storniert.")).toBeInTheDocument());
    expect(prompt).toHaveBeenCalledTimes(2);
    expect(JSON.parse(fetchMock.mock.calls[3]?.[1]?.body as string)).toEqual({ reason: "Einheiten korrigiert" });
  });

  it("files the fee invoice PDF and then offers the download (Q15)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    mockLoad(fetchMock, [period("issued")], [invoice]);
    fetchMock.mockResolvedValueOnce(jsonResponse({ document_id: "0192abcd-0000-7000-8000-00000000d001", created: true }, 201));
    renderIntl(<AdminFeePanel properties={[{ id: "p1", label: "P022 Honorarhaus" }]} today="2026-02-15" />);
    await userEvent.click(await screen.findByRole("button", { name: "PDF erzeugen" }));
    const link = await screen.findByRole("link", { name: "PDF herunterladen" });
    expect(link).toHaveAttribute("href", "/api/handover-files/documents/0192abcd-0000-7000-8000-00000000d001/content");
    expect(fetchMock.mock.calls[3]?.[0]).toBe(`/api/bff/accounting/admin-fee-invoices/${INV}/document`);
  });

  it("creates posting drafts for a released invoice and filters by status (M13-07)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const released = { ...invoice, status: "released", released_at: "2026-04-03T08:00:00Z", payer_entry_id: null };
    mockLoad(fetchMock, [], [released]);
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ invoice_id: INV, payer_entry_id: "e1", manager_entry_id: "e2", created: true }, 201),
    );
    mockLoad(fetchMock, [], [{ ...released, payer_entry_id: "e1" }]);
    renderIntl(<AdminFeePanel properties={[]} today="2026-02-15" />);
    await userEvent.click(await screen.findByRole("button", { name: "Buchungsentwurf" }));
    expect(fetchMock.mock.calls[3]?.[0]).toBe(`/api/bff/accounting/admin-fee-invoices/${INV}/posting-drafts`);
    expect(await screen.findByText("Entwurf angelegt")).toBeInTheDocument();
    mockLoad(fetchMock, [], []);
    await userEvent.selectOptions(screen.getByTestId("fee-status-filter"), "cancelled");
    await waitFor(() =>
      expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith("/admin-fee-invoices?status=cancelled"))).toBe(true),
    );
  });
});
