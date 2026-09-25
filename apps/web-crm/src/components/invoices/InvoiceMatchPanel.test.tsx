import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InvoiceMatchPanel } from "./InvoiceMatchPanel";

const INVOICE_ID = "0192abcd-0000-7000-8000-000000000010";

describe("InvoiceMatchPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows a matched transaction and offers no proposal form", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse([{ id: "l-1", bank_transaction_id: "t-1", match_basis: "amount_and_number", amount: "1190.00" }]),
    );
    renderIntl(<InvoiceMatchPanel invoiceId={INVOICE_ID} />);
    expect(await screen.findByTestId("invoice-match-panel")).toBeInTheDocument();
    expect(screen.getByText(/1.190,00/)).toBeInTheDocument();
    expect(screen.queryByText("Zahlung vorbereiten")).not.toBeInTheDocument();
  });

  it("creates a draft payment proposal marked as prepared, not executed", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return jsonResponse([]);
      expect(JSON.parse(String(init?.body))).toEqual({
        bank_account_id: "0192abcd-0000-7000-8000-000000000099",
        execution_date: "2026-04-01",
      });
      return jsonResponse({
        invoice_id: INVOICE_ID,
        matches: [],
        proposal: { id: "order-1", status: "draft" },
        proposal_note: "vorbereitet, nicht ausgeführt",
      });
    });
    renderIntl(<InvoiceMatchPanel invoiceId={INVOICE_ID} />);
    await screen.findByText("Kein passender Bankumsatz gefunden.");
    await userEvent.type(screen.getByLabelText("ID des internen Kontos"), "0192abcd-0000-7000-8000-000000000099");
    await userEvent.type(screen.getByLabelText("Ausführungsdatum"), "2026-04-01");
    await userEvent.click(screen.getByRole("button", { name: "Zahlung vorbereiten" }));
    expect(await screen.findByText("vorbereitet, nicht ausgeführt")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalled();
  });
});
