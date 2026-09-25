import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InvoiceExtract } from "./InvoiceExtract";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const PROPOSAL = "01920000-0000-7000-8000-00000000f001";
const LEDGER = "01920000-0000-7000-8000-00000000f002";
const ACCOUNT = "01920000-0000-7000-8000-00000000f003";
const PROVIDER = "01920000-0000-7000-8000-00000000f004";
const DOC = "01920000-0000-7000-8000-00000000f005";

const PROPOSAL_BODY = {
  id: PROPOSAL,
  task_run_id: "01920000-0000-7000-8000-00000000f006",
  entity_type: "invoice",
  context_id: null,
  proposed: {
    invoice: {
      supplier_name: "Handwerker Muster",
      iban: "...3000",
      invoice_number: "RE-2026-1",
      invoice_date: "2026-03-01",
      due_date: "2026-03-15",
      net: "500.00",
      vat: "95.00",
      gross: "595.00",
      currency: "EUR",
      discount_percent: null,
      discount_until: null,
      order_reference: "AUF-9",
      property_number_guess: "Musterhaus",
      warnings: ["IBAN weicht ab: gesonderte Bestätigung nötig."],
      confidence: 0.87,
    },
    supplier_candidates: [{ contact_id: PROVIDER, name: "Handwerker Muster", score: 0.9, reasons: ["Name ähnlich"] }],
    warnings: [],
    questions: [],
    document_ids: [DOC],
  },
  decision: "pending",
  decided_by: null,
  decided_at: null,
  import_run_id: null,
};

const LEDGERS = [{ id: LEDGER, label: "Buchungskreis A" }];
const ACCOUNTS = { [LEDGER]: [{ id: ACCOUNT, label: "040100 Instandhaltung" }] };

describe("InvoiceExtract review form", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders the extracted fields with a masked IBAN and requires the confirmation field", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith(`/api/bff/ai/proposals/${PROPOSAL}`)) return jsonResponse(PROPOSAL_BODY);
      throw new Error(`unexpected fetch ${url}`);
    });

    renderIntl(<InvoiceExtract ledgers={LEDGERS} accounts={ACCOUNTS} initialProposalId={PROPOSAL} />);

    await waitFor(() => expect(screen.getByTestId("invoice-review-form")).toBeInTheDocument());
    expect(screen.getByDisplayValue("...3000")).toBeDisabled();
    expect(screen.getByText(/IBAN weicht ab/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Als Entwurf anlegen/ })).toBeDisabled();
  });

  it("enables apply only once the IBAN confirmation and required fields are filled, and posts the confirmed body", async () => {
    const calls: { url: string; body: unknown }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith(`/api/bff/ai/proposals/${PROPOSAL}`) && method === "GET") return jsonResponse(PROPOSAL_BODY);
      if (url.endsWith(`/api/bff/ai/proposals/${PROPOSAL}/apply`) && method === "POST") {
        calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
        return jsonResponse({ id: "run1", source: "ai:extract_invoice", status: "applied", document_ids: [], summary: {}, items: [{ sequence: 1, entity_type: "invoice", entity_id: "01920000-0000-7000-8000-00000000f099", undone: false, kept_reason: null }], undone_at: null, undone_by: null }, 201);
      }
      throw new Error(`unexpected fetch ${url} ${method}`);
    });

    const user = userEvent.setup();
    renderIntl(<InvoiceExtract ledgers={LEDGERS} accounts={ACCOUNTS} initialProposalId={PROPOSAL} />);
    await waitFor(() => expect(screen.getByTestId("invoice-review-form")).toBeInTheDocument());

    const submit = screen.getByRole("button", { name: /Als Entwurf anlegen/ });
    expect(submit).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("Aussteller"), PROVIDER);
    await user.type(screen.getByLabelText(/IBAN aus dem Original eintragen/), "DE89370400440532013000");
    await user.selectOptions(screen.getByLabelText("Kostenkonto"), ACCOUNT);
    expect(submit).toBeEnabled();

    await user.click(submit);
    await waitFor(() => expect(calls.length).toBe(1));
    const body = calls[0]!.body as { invoice: Record<string, unknown> };
    expect(body.invoice.payee_iban).toBe("DE89370400440532013000");
    expect(body.invoice.provider_contact_id).toBe(PROVIDER);
    expect(body.invoice.ledger_id).toBe(LEDGER);
    expect(body.invoice.document_id).toBe(DOC);
    expect(body.invoice.currency).toBe("EUR");
  });

  it("blocks apply and shows a German message when the extracted currency is not EUR", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith(`/api/bff/ai/proposals/${PROPOSAL}`))
        return jsonResponse({
          ...PROPOSAL_BODY,
          proposed: { ...PROPOSAL_BODY.proposed, invoice: { ...PROPOSAL_BODY.proposed.invoice, currency: "USD" } },
        });
      throw new Error(`unexpected fetch ${url}`);
    });

    renderIntl(<InvoiceExtract ledgers={LEDGERS} accounts={ACCOUNTS} initialProposalId={PROPOSAL} />);
    await waitFor(() => expect(screen.getByTestId("invoice-review-form")).toBeInTheDocument());
    expect(screen.getByRole("alert")).toHaveTextContent(/Fremdwährung/);
    expect(screen.getByRole("button", { name: /Als Entwurf anlegen/ })).toBeDisabled();
  });
});
