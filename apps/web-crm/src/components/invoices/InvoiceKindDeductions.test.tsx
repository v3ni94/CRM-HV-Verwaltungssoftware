import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { jsonResponse, renderIntl } from "@/test/intl";
import type { Deduction } from "@/lib/invoice-lines";

import { InvoiceKindDeductions, type InvoiceKindValue } from "./InvoiceKindDeductions";

function Harness() {
  const [kind, setKind] = useState<InvoiceKindValue>("invoice");
  const [d, setD] = useState<Deduction[]>([]);
  return <InvoiceKindDeductions ledgerId="l1" providerId="p1" kind={kind} finalGross="5950.00" deductions={d} onKind={setKind} onDeductions={setD} />;
}

describe("InvoiceKindDeductions (GAM-105, D12)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists booked progress invoices of the issuer and shows 3.570,00 EUR remaining", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([{ id: "x1", number: "A-1", invoice_date: "2026-01-10", gross: "2380.00" }]));
    renderIntl(<Harness />);
    expect(screen.queryByTestId("deduction-list")).toBeNull();
    await userEvent.selectOptions(screen.getByLabelText("Rechnungsart"), "final");
    const box = await screen.findByRole("checkbox");
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("filter[kind]=partial");
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("filter[posting_status]=posted");
    await userEvent.click(box);
    await waitFor(() => expect(screen.getByTestId("final-summary")).toHaveTextContent("Leistungssumme 5.950,00 EUR, Abzug Abschläge 2.380,00 EUR, Restverpflichtung 3.570,00 EUR"));
  });

  it("asks for the issuer first", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    renderIntl(<InvoiceKindDeductions ledgerId="l1" providerId="" kind="final" finalGross="10.00" deductions={[]} onKind={() => {}} onDeductions={() => {}} />);
    expect(screen.getByText("Zuerst den Aussteller wählen.")).toBeInTheDocument();
  });
});
