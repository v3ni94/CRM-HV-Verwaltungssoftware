import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { RentInvoicePanel, type RentInvoiceOut } from "./RentInvoicePanel";

const invoice: RentInvoiceOut = {
  id: "i1",
  number: "MR-2026-000001",
  kind: "invoice",
  status: "issued",
  invoice_date: "2026-06-05",
  period_start: "2026-06-01",
  period_end: "2026-06-30",
  net_total: "1000.00",
  vat_total: "190.00",
  gross_total: "1190.00",
  draft: true,
  document_id: "d1",
  cancels_invoice_id: null,
  cancelled_by_invoice_id: null,
  hinweis: "Entwurf",
};

describe("RentInvoicePanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing without a VAT option on the contract", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<RentInvoicePanel contractId="c1" vatOption="none" canUpdate={true} />);
    expect(screen.queryByTestId("rent-invoices")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("lists invoices with amounts, draft badge and PDF link", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([invoice]));
    renderIntl(<RentInvoicePanel contractId="c1" vatOption="commercial_full_vat" canUpdate={false} />);
    expect(await screen.findByText("MR-2026-000001")).toBeInTheDocument();
    expect(screen.getByText("1.190,00 EUR")).toBeInTheDocument();
    expect(screen.getByText("Entwurf")).toBeInTheDocument();
    expect(screen.getByText("PDF").getAttribute("href")).toBe("/api/bff/contracts/c1/rent-invoices/i1/pdf");
    expect(screen.getByText("PDF")).not.toHaveAttribute("target");
    expect(screen.queryByText("Mietrechnung erzeugen")).not.toBeInTheDocument();
    expect(screen.queryByText("Gutschrift")).not.toBeInTheDocument();
  });

  it("creates an invoice for the month and a credit note", async () => {
    const calls: { url: string; body: string | null }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, body: typeof init?.body === "string" ? init.body : null });
      if (init?.method === "POST") return jsonResponse(invoice, 201);
      if (url.endsWith("/numbering-mode")) return jsonResponse({ mode: "draft_numbers" });
      return jsonResponse(calls.filter((c) => c.url.endsWith("/rent-invoices")).length > 1 ? [invoice] : []);
    });
    renderIntl(<RentInvoicePanel contractId="c1" vatOption="commercial_full_vat" canUpdate={true} />);
    expect(await screen.findByText("Noch keine Mietrechnung zu diesem Vertrag.")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Monat"));
    await userEvent.type(screen.getByLabelText("Monat"), "2026-06");
    await userEvent.click(screen.getByText("Mietrechnung erzeugen"));
    await waitFor(() => expect(screen.getByText("MR-2026-000001")).toBeInTheDocument());
    const post = calls.find((c) => c.body);
    expect(post?.url).toBe("/api/bff/contracts/c1/rent-invoices");
    expect(JSON.parse(post?.body ?? "{}")).toEqual({ period_start: "2026-06-01", period_end: "2026-06-30", standing: false });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await userEvent.click(screen.getByText("Gutschrift"));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/rent-invoices/i1/credit-note"))).toBe(true));
  });

  it("switches the draft numbering mode via PUT", async () => {
    const calls: { url: string; method?: string; body: string | null }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, method: init?.method, body: typeof init?.body === "string" ? init.body : null });
      if (url.endsWith("/numbering-mode")) return jsonResponse({ mode: init?.method === "PUT" ? "regular_numbers" : "draft_numbers" });
      return jsonResponse([]);
    });
    renderIntl(<RentInvoicePanel contractId="c1" vatOption="commercial_full_vat" canUpdate={true} />);
    const select = await screen.findByLabelText("Nummer für Entwürfe");
    await userEvent.selectOptions(select, "regular_numbers");
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.url).toBe("/api/bff/accounting/rent-invoices/numbering-mode");
    expect(JSON.parse(put?.body ?? "{}")).toEqual({ mode: "regular_numbers" });
  });
});
