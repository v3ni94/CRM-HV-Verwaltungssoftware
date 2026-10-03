import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InvoiceDiscountPreview } from "./InvoiceDiscountPreview";

describe("InvoiceDiscountPreview (GAL-304)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing without discount terms", () => {
    const { container } = renderIntl(<InvoiceDiscountPreview invoiceId="i1" discountPercent={null} discountUntil={null} today="2026-03-01" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("previews discount and payable amount for the payment date, read only", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ discount: "119.00", payable: "5831.00" }));
    renderIntl(<InvoiceDiscountPreview invoiceId="i1" discountPercent="2" discountUntil="2026-03-10" today="2026-03-05" />);
    await userEvent.click(screen.getByText("Zahlbetrag berechnen"));
    await waitFor(() => expect(screen.getByTestId("discount-result")).toHaveTextContent("Skonto 119,00 EUR, Zahlbetrag 5.831,00 EUR"));
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/bff/accounting/invoices/i1/discount?pay_date=2026-03-05");
    expect(fetchMock.mock.calls[0]?.[1]?.method ?? "GET").toBe("GET");
  });

  it("states that the period has ended after the discount date", () => {
    renderIntl(<InvoiceDiscountPreview invoiceId="i1" discountPercent="2" discountUntil="2026-03-10" today="2026-03-11" />);
    expect(screen.getByTestId("discount-expired")).toBeInTheDocument();
  });
});
