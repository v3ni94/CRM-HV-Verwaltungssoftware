import { screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InvoiceFactualPanel } from "./InvoiceFactualPanel";

const INVOICE_ID = "0192abcd-0000-7000-8000-000000000010";

describe("InvoiceFactualPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists findings by area and the proposed property manager", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({
        invoice_id: INVOICE_ID,
        version: 1,
        findings: [
          { area: "price", code: "price_quote", message: "Rechnungsbetrag weicht vom Angebot ab" },
          { area: "budget", code: "budget_exceeded", message: "Planansatz überschritten" },
        ],
        suggested_reviewer_user_id: "u-1",
        property_id: null,
        price_tolerance_percent: "2.5",
        quantity_tolerance_percent: "0",
        automatic_release: false,
      }),
    );
    renderIntl(<InvoiceFactualPanel invoiceId={INVOICE_ID} />);
    expect(await screen.findByText("Preis: Rechnungsbetrag weicht vom Angebot ab")).toBeInTheDocument();
    expect(screen.getByText("Budget: Planansatz überschritten")).toBeInTheDocument();
    expect(screen.getByText("Vorschlag Zuständigkeit: Objektverwalter: u-1")).toBeInTheDocument();
    expect(screen.getByText("Toleranz Preis 2,5 %, Menge 0 %")).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/accounting/invoices/${INVOICE_ID}/factual-check`);
  });

  it("shows the empty state and the problem detail", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({
        findings: [],
        suggested_reviewer_user_id: null,
        price_tolerance_percent: "0",
        quantity_tolerance_percent: "0",
      }),
    );
    renderIntl(<InvoiceFactualPanel invoiceId={INVOICE_ID} />);
    expect(await screen.findByText(/Keine Befunde/)).toBeInTheDocument();
    expect(screen.getByText("Kein Zuständigkeitsvorschlag")).toBeInTheDocument();
  });

  it("shows an error", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ title: "Berechtigung", status: 403, detail: "Es fehlt accounting:read." }, 403),
    );
    renderIntl(<InvoiceFactualPanel invoiceId={INVOICE_ID} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("accounting:read");
  });
});
