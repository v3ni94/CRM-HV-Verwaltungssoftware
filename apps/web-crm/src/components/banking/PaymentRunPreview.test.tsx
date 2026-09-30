import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankStatusImport } from "./BankStatusImport";
import { PaymentRunPreview, type PaymentRunPreviewData } from "./PaymentRunPreview";

const preview: PaymentRunPreviewData = {
  as_of: "2026-10-01",
  until: "2026-10-08",
  verification_of_payee: "Empfängerüberprüfung (Verification of Payee) zu verifizieren.",
  legal_entities: [
    {
      legal_entity_id: "le1",
      legal_entity_name: "GdWE Musterhaus",
      bank_accounts: [
        { id: "ba1", iban_suffix: "2051", holder: "GdWE", limits: { single_order_limit: null, daily_limit: "1000.00" } },
      ],
      total: "600.00",
      invoices: [
        {
          invoice_id: "i1",
          number: "R-1",
          payee: "Dienst GmbH",
          iban_suffix: "3000",
          due_date: "2026-10-03",
          overdue: false,
          remaining: "600.00",
          eligible: true,
          block_reason: null,
        },
        {
          invoice_id: "i2",
          number: "R-2",
          payee: "Ohne IBAN GmbH",
          iban_suffix: null,
          due_date: "2026-09-20",
          overdue: true,
          remaining: "90.00",
          eligible: false,
          block_reason: "Rechnung ohne Empfänger-IBAN",
        },
      ],
    },
  ],
  direct_debit_runs: [
    { run_id: "r1", status: "approved", collection_date: "2026-10-05", control_sum: "350.00", transaction_count: 1, pre_notifications_missing: 1 },
  ],
};

describe("PaymentRunPreview", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists invoices per legal entity and creates draft orders for the selection", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(preview))
      .mockResolvedValueOnce(
        jsonResponse({ created: [{ id: "o1" }], failed: [], limit_warnings: ["Tageslimit überschritten"] }, 201),
      )
      .mockResolvedValueOnce(jsonResponse({ ...preview, legal_entities: [] }));
    renderIntl(<PaymentRunPreview />);
    expect(await screen.findByText("GdWE Musterhaus")).toBeInTheDocument();
    expect(screen.getByText("Rechnung ohne Empfänger-IBAN")).toBeInTheDocument();
    expect(screen.getByLabelText("Rechnung R-2 auswählen")).toBeDisabled();
    expect(screen.getByTestId("vop-note")).toHaveTextContent("Verification of Payee");
    await userEvent.click(screen.getByLabelText("Rechnung R-1 auswählen"));
    await userEvent.click(screen.getByText("1 Aufträge als Entwurf anlegen"));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("1 Aufträge angelegt"));
    const init = fetchMock.mock.calls[1]?.[1];
    const body = JSON.parse(String((init as RequestInit).body));
    expect(body.items).toEqual([{ invoice_id: "i1", property_bank_account_id: "ba1" }]);
    expect(screen.getByRole("status")).toHaveTextContent("Tageslimit überschritten");
  });

  it("shows the problem when the preview fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ title: "Verboten", status: 403, detail: "Keine Berechtigung." }, 403),
    );
    renderIntl(<PaymentRunPreview />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("BankStatusImport", () => {
  afterEach(() => vi.restoreAllMocks());

  it("uploads the XML and shows the per line result", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(
        {
          id: "rep1",
          kind: "pain.002",
          created: true,
          result: [{ end_to_end_id: "E2E1", reported: "rejected", reason_code: "AC04", amount: null, result: "abgelehnt, Posten bleibt offen" }],
        },
        201,
      ),
    );
    renderIntl(<BankStatusImport />);
    const file = new File(["<Document/>"], "status.xml", { type: "text/xml" });
    await userEvent.upload(screen.getByLabelText("XML-Datei"), file);
    expect(await screen.findByRole("status")).toHaveTextContent("E2E1 rejected (AC04): abgelehnt, Posten bleibt offen");
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/bff/accounting/payment-runs/bank-status-reports");
  });
});
