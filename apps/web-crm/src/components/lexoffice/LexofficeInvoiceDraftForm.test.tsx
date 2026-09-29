import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LexofficeInvoiceDraftForm } from "./LexofficeInvoiceDraftForm";

const CONTACT = "01920000-0000-7000-8000-0000000000c1";

function mockApi() {
  const calls: { url: string; body: unknown }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (url.endsWith("/invoice-drafts/preview"))
      return jsonResponse({
        config_id: "cfg-1",
        legal_entity_id: "le-1",
        legal_entity_name: "Hausverwaltung",
        payload: {},
        address_from_link: true,
        net: "200,00 EUR",
        tax: "38,00 EUR",
        gross: "238,00 EUR",
        note: "Summen werden von Lexware Office berechnet, Anzeige zur Kontrolle",
      });
    if (url.endsWith("/invoice-drafts")) return jsonResponse({ id: "d1", status: "queued", deeplink: null, last_error: null }, 202);
    return jsonResponse({ title: "unerwartet" }, 500);
  });
  return calls;
}

describe("LexofficeInvoiceDraftForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows local sums, previews via the API and only then submits the draft as decimal strings", async () => {
    const calls = mockApi();
    const user = userEvent.setup();
    renderIntl(<LexofficeInvoiceDraftForm contactId={CONTACT} contactName="Erika Muster" />);
    expect(screen.getByText("Kontakt: Erika Muster")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Als Entwurf anlegen" })).toBeDisabled();

    await user.type(screen.getByLabelText("Bezeichnung"), "Verwaltervergütung");
    await user.clear(screen.getByLabelText("Menge"));
    await user.type(screen.getByLabelText("Menge"), "2");
    await user.type(screen.getByLabelText("Einzelpreis"), "100,00");
    await waitFor(() => expect(screen.getByTestId("lexoffice-draft-local-sums")).toHaveTextContent("238,00 EUR"));
    expect(screen.getByRole("button", { name: "Als Entwurf anlegen" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Vorschau prüfen" }));
    await waitFor(() => expect(screen.getByTestId("lexoffice-draft-preview")).toHaveTextContent("Hausverwaltung"));
    expect(screen.getByTestId("lexoffice-draft-preview")).toHaveTextContent("Adresse aus der Lexware Verknüpfung");
    const previewCall = calls.find((c) => c.url.endsWith("/invoice-drafts/preview"))!;
    expect(previewCall.body).toMatchObject({
      invoice_kind: "management",
      contact_id: CONTACT,
      tax_type: "net",
      line_items: [{ name: "Verwaltervergütung", quantity: "2", unit_price: "100.00", tax_rate_percent: 19, unit_name: "Stück" }],
      shipping: { type: "none", date: null, end_date: null },
    });

    await user.click(screen.getByRole("button", { name: "Als Entwurf anlegen" }));
    await waitFor(() => expect(screen.getByTestId("lexoffice-draft-created")).toBeInTheDocument());
    expect(calls.filter((c) => c.url.endsWith("/invoice-drafts")).length).toBe(1);
  });

  it("blocks vatfree with a tax rate above zero and requires service dates", async () => {
    mockApi();
    const user = userEvent.setup();
    renderIntl(<LexofficeInvoiceDraftForm contactId={null} />);
    expect(screen.getByText("Kontakt: Kein Kontakt gewählt, die Adresse wird nicht übernommen.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Bezeichnung"), "Beratung");
    await user.type(screen.getByLabelText("Einzelpreis"), "50");
    await user.selectOptions(screen.getByLabelText("Steuerart"), "vatfree");
    expect(screen.getByText("Steuerfreie Rechnungen erlauben nur 0 Prozent.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Vorschau prüfen" })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Steuersatz"), "0");
    expect(screen.getByRole("button", { name: "Vorschau prüfen" })).toBeEnabled();
    await user.selectOptions(screen.getByLabelText("Leistung"), "serviceperiod");
    expect(screen.getByRole("button", { name: "Vorschau prüfen" })).toBeDisabled();
    await user.type(screen.getByLabelText("Leistungsdatum"), "2026-09-01");
    await user.type(screen.getByLabelText("Ende"), "2026-09-30");
    expect(screen.getByRole("button", { name: "Vorschau prüfen" })).toBeEnabled();
  });

  it("marks an invalid amount", async () => {
    mockApi();
    const user = userEvent.setup();
    renderIntl(<LexofficeInvoiceDraftForm contactId={null} />);
    await user.type(screen.getByLabelText("Bezeichnung"), "X");
    await user.type(screen.getByLabelText("Einzelpreis"), "12,34567");
    expect(screen.getByText("Ungültiger Betrag")).toBeInTheDocument();
  });
});
