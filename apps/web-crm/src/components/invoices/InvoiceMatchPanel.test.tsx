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
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const method = init?.method ?? "GET";
      if (method === "GET" && String(input).startsWith("/api/bff/banking/accounts")) return jsonResponse([ACCOUNT]);
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
    expect(screen.getByText(/Zahlungsdatei bleibt bis G2 gesperrt/)).toBeInTheDocument();
    const propose = screen.getByRole("button", { name: "Zahlung vorbereiten" });
    expect(propose).toBeDisabled();
    await userEvent.click(screen.getByRole("combobox", { name: "Bankkonto (Rechtsträger)" }));
    await userEvent.click(await screen.findByRole("option"));
    await userEvent.type(screen.getByLabelText("Ausführungsdatum"), "2026-04-01");
    await userEvent.click(propose);
    expect(await screen.findByText("vorbereitet, nicht ausgeführt")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalled();
  });

  it("shows a loading state and then the problem detail when the list cannot be read", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ title: "Berechtigung", status: 403, detail: "Für diese Aktion fehlt die Berechtigung accounting:read." }, 403),
    );
    renderIntl(<InvoiceMatchPanel invoiceId={INVOICE_ID} />);
    expect(screen.getByRole("status")).toHaveTextContent("Bankabgleich wird geladen.");
    expect(await screen.findByRole("alert")).toHaveTextContent("accounting:read");
  });
});

const ACCOUNT = {
  id: "0192abcd-0000-7000-8000-000000000099",
  property_id: "0192abcd-0000-7000-8000-000000000001",
  property_number: "0001",
  property_name: "Testweg 1",
  legal_entity_id: "le-1",
  legal_entity_name: "GdWE Testweg",
  legal_entity_kind: "hoa",
  kind: "current",
  iban_masked: "DE02 **** **** 2051",
  bic: null,
  bank_name: "Sparkasse",
  holder: "GdWE Testweg",
  valid_from: "2024-01-01",
  valid_to: null,
  source: "manual" as const,
  balance: null,
  balance_as_of: null,
  balance_source: null,
  default_for_legal_entity: true,
  assignments: [],
  recent_transactions: [],
};
