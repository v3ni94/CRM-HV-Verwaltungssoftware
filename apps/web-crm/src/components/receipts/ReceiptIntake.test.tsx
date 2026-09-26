import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { minConfidence, ReceiptIntake, type ReceiptDraft } from "./ReceiptIntake";

function field(value: string | null, confidence = 0.9, source: "ai" | "xml" | "ai_estimate" | "local" | "none" = "ai") {
  return { value, confidence, source, note: null };
}

function makeDraft(overrides: Partial<ReceiptDraft>): ReceiptDraft {
  return {
    id: "draft-1",
    document_id: "doc-1",
    source: "mail_attachment",
    status: "proposed",
    fields: {
      supplier_name: field("Heizungsbau Schmidt GmbH", 0.95),
      invoice_number: field("RE-2026-100", 0.9),
      invoice_date: field("2026-09-15", 0.88),
      due_date: field("2026-09-29", 0.7),
      net: field("100.00", 0.92),
      vat: field("19.00", 0.92),
      gross: field("119.00", 0.92),
      currency: field("EUR", 1, "local"),
      discount_percent: field(null, 0, "none"),
      discount_until: field(null, 0, "none"),
      order_reference: field(null, 0, "none"),
      property_ref: field("prop-1", 0.55, "local"),
    },
    iban_candidates: [{ masked: "DE12 **** **** **** **** 34", checksum_ok: true, source: "local" }],
    supplier_candidates: [{ contact_id: "c-1", name: "Heizungsbau Schmidt GmbH", score: 0.9, reasons: [] }],
    property_suggestions: [{ property_id: "prop-1", number: "0001", name: "Musterstraße 1", score: 0.55, reason: "Adresse" }],
    warnings: [],
    questions: [],
    masked_excerpt: null,
    error: null,
    invoice_id: null,
    created_at: "2026-09-20T08:00:00Z",
    ...overrides,
  };
}

const ledgers = [{ id: "ledger-1", label: "HVM" }];
const accounts = { "ledger-1": [{ id: "acc-1", label: "4200 Heizung" }] };

function renderIntake(drafts: ReceiptDraft[], initialDraftId: string | null = null) {
  return renderIntl(<ReceiptIntake initialDrafts={drafts} initialDraftId={initialDraftId} ledgers={ledgers} accounts={accounts} />);
}

async function fillRequired() {
  await userEvent.selectOptions(screen.getByLabelText("Sachkonto"), "acc-1");
}

describe("minConfidence", () => {
  it("returns the lowest field confidence", () => {
    expect(minConfidence(makeDraft({}))).toBe(0);
    expect(minConfidence(makeDraft({ fields: { gross: field("1", 0.8), net: field("1", 0.6) } }))).toBe(0.6);
    expect(minConfidence(makeDraft({ fields: {} }))).toBeNull();
  });
});

describe("ReceiptIntake", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists drafts with issuer, amount, date, property, confidence and source, open filter by default", async () => {
    const older = makeDraft({ id: "draft-2", status: "confirmed", created_at: "2026-09-19T08:00:00Z", fields: { supplier_name: field("Alt GmbH", 0.4) } });
    renderIntake([older, makeDraft({})]);
    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent("Heizungsbau Schmidt GmbH");
    expect(rows[0]).toHaveTextContent("119,00 EUR");
    expect(rows[0]).toHaveTextContent("15.09.2026");
    expect(rows[0]).toHaveTextContent("0001 Musterstraße 1");
    expect(rows[0]).toHaveTextContent("Mail-Anhang");
    expect(rows[0]).toHaveTextContent("0 %");
    expect(screen.getByRole("columnheader", { name: "Sicherheit" })).toHaveAttribute("title", "niedrigste Feldsicherheit");

    await userEvent.click(screen.getByRole("button", { name: "Alle" }));
    const all = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(all).toHaveLength(2);
    expect(all[0]).toHaveTextContent("Heizungsbau Schmidt GmbH");
    expect(all[1]).toHaveTextContent("Alt GmbH");
    expect(all[1]).toHaveTextContent("40 %");
  });

  it("confirms with the reviewed value instead of the proposal", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/confirm")) {
        const body = JSON.parse(String(init?.body));
        expect(body.iban_confirmed).toBe(false);
        expect(body.invoice.payee_iban).toBeNull();
        expect(body.invoice.number).toBe("RE-2026-100-KORR");
        expect(body.invoice.provider_contact_id).toBe("c-1");
        expect(body.invoice.lines).toEqual([{ account_id: "acc-1", net: "100.00", vat_percent: "19", vat: "19.00" }]);
        return jsonResponse(makeDraft({ status: "confirmed", invoice_id: "inv-1" }), 201);
      }
      throw new Error(`unexpected ${String(input)}`);
    });
    renderIntake([makeDraft({})], "draft-1");
    const review = screen.getByTestId("receipt-review");
    expect(within(review).getByText("RE-2026-100")).toBeInTheDocument();
    const numberInput = within(review).getByDisplayValue("RE-2026-100");
    await userEvent.clear(numberInput);
    await userEvent.type(numberInput, "RE-2026-100-KORR");
    await fillRequired();
    await userEvent.click(screen.getByRole("button", { name: "Rechnung als Entwurf anlegen" }));
    expect(await screen.findByText("Rechnungsentwurf angelegt.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Rechnungsentwurf öffnen" })).toHaveAttribute("href", "/rechnungen/inv-1");
    expect(fetchMock).toHaveBeenCalledWith("/api/bff/receipts/drafts/draft-1/confirm", expect.objectContaining({ method: "POST" }));
  });

  it("takes an IBAN only with the explicit confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      const body = JSON.parse(String(init?.body));
      expect(body.iban_confirmed).toBe(true);
      expect(body.invoice.payee_iban).toBe("DE02120300000000202051");
      return jsonResponse(makeDraft({ status: "confirmed", invoice_id: "inv-2" }), 201);
    });
    renderIntake([makeDraft({})], "draft-1");
    await fillRequired();
    const confirm = screen.getByRole("button", { name: "Rechnung als Entwurf anlegen" });
    expect(confirm).toBeEnabled();
    expect(screen.getByText("DE12 **** **** **** **** 34")).toBeInTheDocument();
    const checkbox = screen.getByRole("checkbox", { name: /Ich habe die IBAN mit dem Originalbeleg verglichen/ });
    expect(checkbox).toBeDisabled();
    await userEvent.type(screen.getByLabelText("IBAN aus dem Original eintragen"), "DE02120300000000202051");
    expect(confirm).toBeDisabled();
    await userEvent.click(checkbox);
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    expect(await screen.findByText("Rechnungsentwurf angelegt.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("rejects a draft with the given reason", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      expect(JSON.parse(String(init?.body))).toEqual({ reason: "Doppelt" });
      return jsonResponse(makeDraft({ status: "rejected" }));
    });
    renderIntake([makeDraft({})], "draft-1");
    await userEvent.type(screen.getByLabelText("Grund (optional)"), "Doppelt");
    await userEvent.click(screen.getByRole("button", { name: "Entwurf verwerfen" }));
    expect(await screen.findByText("Über diesen Entwurf wurde bereits entschieden.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/bff/receipts/drafts/draft-1/reject", expect.objectContaining({ method: "POST" }));
    expect(screen.queryByRole("button", { name: "Rechnung als Entwurf anlegen" })).not.toBeInTheDocument();
  });

  it("shows the API problem and keeps the draft open", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ title: "Konflikt", detail: "Über den Belegentwurf wurde bereits entschieden.", status: 409 }, 409),
    );
    renderIntake([makeDraft({})], "draft-1");
    await fillRequired();
    await userEvent.click(screen.getByRole("button", { name: "Rechnung als Entwurf anlegen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Über den Belegentwurf wurde bereits entschieden.");
    expect(screen.getByRole("button", { name: "Rechnung als Entwurf anlegen" })).toBeEnabled();
  });

  it("shows the failure reason of a failed extraction", () => {
    renderIntake([makeDraft({ status: "failed", error: "Anhang nicht lesbar" })], "draft-1");
    expect(screen.getByRole("alert")).toHaveTextContent("Die Extraktion ist fehlgeschlagen: Anhang nicht lesbar");
  });

  it("D42: shows XML as source per field, lists conflicts and confirms only after they were seen", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/confirm")) {
        const body = JSON.parse(String(init?.body));
        expect(body.conflicts_acknowledged).toBe(true);
        expect(body.invoice.number).toBe("RE-2026-100");
        expect(body.invoice).not.toHaveProperty("recipient_name");
        expect(body.invoice).not.toHaveProperty("section_35a_amount");
        return jsonResponse(makeDraft({ status: "confirmed", invoice_id: "inv-1" }), 201);
      }
      throw new Error(`unexpected ${String(input)}`);
    });
    const draft = makeDraft({
      e_invoice_format: "zugferd",
      fields: {
        ...makeDraft({}).fields,
        invoice_number: field("RE-2026-100", 1, "xml"),
        gross: field("119.00", 1, "xml"),
        recipient_name: field("WEG Musterstraße 1", 1, "xml"),
      },
      conflicts: [
        { field: "invoice_number", xml: "RE-2026-100", other: null, other_source: "pdf_text", note: "Rechnungsnummer aus dem XML kommt im PDF-Text nicht vor." },
        { field: "gross", xml: "119.00", other: "190.00", other_source: "ai", note: "XML und PDF-Text (KI-Lesung) nennen unterschiedliche Werte." },
      ],
      findings: ["Hybridrechnung: XML und PDF widersprechen sich; Zahlungsprüfung erforderlich, keine automatische Auswahl (D42)."],
      xml_lines: [{ position: "1", description: "Arbeitszeit", quantity: "2", unit: "HUR", net: "100.00", vat_percent: "19" }],
      xml_payment: { means_code: "58", payee_name: null, reference: "RE-2026-100", terms: null, iban_masked: "DE12 ... 3456", iban_checksum_ok: true },
    });
    renderIntake([draft], "draft-1");
    const review = screen.getByTestId("receipt-review");
    expect(within(review).getByText("E-Rechnung: ZUGFeRD/Factur-X (PDF mit XML)")).toBeInTheDocument();
    expect(within(review).getAllByText("XML (E-Rechnung)").length).toBeGreaterThanOrEqual(3);
    const conflicts = screen.getByTestId("receipt-conflicts");
    expect(conflicts).toHaveTextContent("Rechnungsnummer: XML RE-2026-100, PDF-Text nicht gefunden.");
    expect(conflicts).toHaveTextContent("Brutto: XML 119.00, KI-Lesung des PDF 190.00.");
    expect(screen.getByTestId("receipt-findings")).toHaveTextContent("Hybridrechnung");
    expect(within(review).getByText("Rechnungsempfänger (laut Beleg)").closest("tr")).toHaveTextContent("nur zur Prüfung, wird nicht übernommen");
    expect(within(review).getAllByRole("row").filter((r) => r.getAttribute("data-conflict") === "true")).toHaveLength(2);
    expect(screen.getByTestId("receipt-xml-payment")).toHaveTextContent("DE12 ... 3456");
    expect(screen.getByTestId("receipt-xml-lines")).toHaveTextContent("Positionen laut XML (1)");

    await fillRequired();
    const confirmButton = screen.getByRole("button", { name: "Rechnung als Entwurf anlegen" });
    expect(confirmButton).toBeDisabled();
    await userEvent.click(screen.getByLabelText(/Ich habe die Widersprüche gesichtet/));
    expect(confirmButton).toBeEnabled();
    await userEvent.click(confirmButton);
    expect(await screen.findByText("Rechnungsentwurf angelegt.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalled();
  });

  it("D44: a § 35a share estimated by the AI is marked as not proven and cannot be edited or taken over", () => {
    const draft = makeDraft({
      fields: {
        ...makeDraft({}).fields,
        section_35a_amount: { value: "300.00", confidence: 0, source: "ai_estimate", note: "KI-Schätzung ohne belegbare Aufteilung; gilt nicht als belegt." },
      },
      findings: ["§-35a-Anteil 300.00 ist nur eine KI-Schätzung und nicht belegt: keine Übernahme, belegbare Aufteilung beim Aussteller nachfordern (PÜ03, D44)."],
    });
    renderIntake([draft], "draft-1");
    const review = screen.getByTestId("receipt-review");
    const row = within(review).getByText("Anteil nach § 35a EStG").closest("tr");
    expect(row).toHaveTextContent("300.00");
    expect(row).toHaveTextContent("KI-Schätzung, nicht belegt");
    expect(row).toHaveTextContent("0 %");
    expect(row).toHaveTextContent("nur zur Prüfung, wird nicht übernommen");
    expect(within(row as HTMLElement).queryByDisplayValue("300.00")).toBeNull();
    expect(screen.getByTestId("receipt-findings")).toHaveTextContent("nur eine KI-Schätzung");
  });
});
