import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LexofficeInvoiceCopyCard, type InvoiceCopyRequest } from "./LexofficeInvoiceCopyCard";

const TICKET = "01920000-0000-7000-8000-00000000f404";
const REQ = "01920000-0000-7000-8000-0000000000e1";
const CONTACT = "01920000-0000-7000-8000-0000000000c1";

const hit = {
  config_id: "cfg-1",
  legal_entity_label: "HVM",
  kind: "invoice",
  lexoffice_invoice_id: "inv-1",
  voucher_number: "RE-1019",
  voucher_date: "2026-08-03",
  total_gross: "238.00",
  status: "paid",
  address_name: "Erika Muster",
  address_contact_id: "lx-1",
  deeplink: "https://app.lexware.de/invoices/inv-1",
};

const request = (patch: Partial<InvoiceCopyRequest> = {}): InvoiceCopyRequest => ({
  id: REQ,
  ticket_id: TICKET,
  message_id: null,
  invoice_number: "RE-1019",
  requester_contact_id: CONTACT,
  recipient_contact_id: CONTACT,
  sender_config_id: "cfg-1",
  status: "found",
  lookup: { status: "found", hits: [hit] },
  verification: { status: "verified", hint_from_address_match: true, warnings: [], recipient: { contact_id: CONTACT, display_name: "Erika Muster", primary_email: "erika@example.com" } },
  document_id: null,
  reply_message_id: null,
  last_error: null,
  created_at: "2026-09-28T10:00:00Z",
  ...patch,
});

function mockApi(rows: InvoiceCopyRequest[], listStatus = 200) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
    if (url.endsWith(`/tickets/${TICKET}/invoice-copies`) && (init?.method ?? "GET") === "GET") return jsonResponse(listStatus === 200 ? rows : { title: "verboten" }, listStatus);
    if (url.endsWith(`/tickets/${TICKET}/invoice-copies`)) return jsonResponse(request({ status: "pending" }), 201);
    if (url.includes(`/invoice-copies/${REQ}/`)) return jsonResponse(request({ status: "fetching" }), 202);
    if (url.startsWith("/api/bff/contacts?")) return jsonResponse({ items: [{ id: CONTACT, display_name: "Erika Muster" }] });
    return jsonResponse({ title: "unerwartet" }, 500);
  });
  return calls;
}

describe("LexofficeInvoiceCopyCard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows status, invoice number, hit and recipient check and accepts only after the click", async () => {
    const calls = mockApi([request()]);
    const user = userEvent.setup();
    renderIntl(<LexofficeInvoiceCopyCard ticketId={TICKET} canUpdate canLinkContacts />);
    await waitFor(() => expect(screen.getByTestId("lexoffice-invoice-copy-status")).toHaveTextContent("Rechnung gefunden"));
    expect(screen.getByTestId("lexoffice-invoice-copy-verification")).toHaveTextContent("Anfragender ist der bekannte Rechnungsempfänger (Rechnungsempfänger: Erika Muster)");
    expect(screen.getByText("Absenderadresse passt zum Empfänger (nur Hinweis)")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Treffer" })).getByText(/HVM: RE-1019 vom 03.08.2026, paid, 238,00 EUR/)).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "PDF abrufen und Antwortentwurf erstellen" }));
    await waitFor(() => expect(screen.getByText("Abruf eingeplant. Der Antwortentwurf erscheint im Mailverlauf.")).toBeInTheDocument());
    expect(calls.find((c) => c.method === "POST")?.url).toBe(`/api/bff/integrations/lexoffice/invoice-copies/${REQ}/accept`);
  });

  it("does not offer accept on a requester mismatch and corrects the requester via contact search", async () => {
    const calls = mockApi([request({ verification: { status: "requester_mismatch", hint_from_address_match: false, warnings: ["Kein Postfach für diese Gesellschaft hinterlegt"] } })]);
    const user = userEvent.setup();
    renderIntl(<LexofficeInvoiceCopyCard ticketId={TICKET} canUpdate canLinkContacts />);
    await waitFor(() => expect(screen.getByTestId("lexoffice-invoice-copy-verification")).toHaveTextContent("Anfragender ist nicht der Rechnungsempfänger"));
    expect(screen.queryByRole("button", { name: "PDF abrufen und Antwortentwurf erstellen" })).not.toBeInTheDocument();
    expect(screen.getByText("Kein Postfach für diese Gesellschaft hinterlegt")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Korrigieren" }));
    await user.type(screen.getByPlaceholderText("Kontakt suchen"), "Erika");
    await user.click(screen.getByRole("button", { name: "Suchen" }));
    await user.click(await screen.findByRole("button", { name: "Erika Muster" }));
    await user.click(screen.getByRole("button", { name: "Korrektur speichern" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/correct"))).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/correct"))?.body).toEqual({ invoice_number: null, requester_contact_id: CONTACT });
  });

  it("links the recipient when unresolved and a contact is picked (contacts:update)", async () => {
    const calls = mockApi([request({ recipient_contact_id: null, verification: { status: "recipient_unresolved" } })]);
    const user = userEvent.setup();
    renderIntl(<LexofficeInvoiceCopyCard ticketId={TICKET} canUpdate canLinkContacts />);
    await user.click(await screen.findByRole("button", { name: "Korrigieren" }));
    await user.type(screen.getByPlaceholderText("Kontakt suchen"), "Erika");
    await user.click(screen.getByRole("button", { name: "Suchen" }));
    await user.click(await screen.findByRole("button", { name: "Erika Muster" }));
    await user.click(screen.getByRole("button", { name: "Empfänger mit diesem Kontakt verknüpfen" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/link-recipient"))).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/link-recipient"))?.body).toEqual({ contact_id: CONTACT });
  });

  it("lets the person choose one of several invoices and reject with a reason", async () => {
    const calls = mockApi([request({ status: "ambiguous", lookup: { status: "ambiguous", hits: [hit, { ...hit, lexoffice_invoice_id: "inv-2", legal_entity_label: "Makler" }] }, verification: { status: "not_found" } })]);
    const user = userEvent.setup();
    renderIntl(<LexofficeInvoiceCopyCard ticketId={TICKET} canUpdate canLinkContacts={false} />);
    const choose = await screen.findAllByRole("button", { name: "Diese Rechnung wählen" });
    expect(choose).toHaveLength(2);
    await user.click(choose[1]!);
    await waitFor(() => expect(calls.find((c) => c.url.endsWith("/correct"))?.body).toEqual({ selected_invoice_id: "inv-2" }));
    await user.click(screen.getByRole("button", { name: "Ablehnen" }));
    expect(screen.getByRole("button", { name: "Ablehnung bestätigen" })).toBeDisabled();
    await user.type(screen.getByLabelText("Grund der Ablehnung"), "Falsche Nummer");
    await user.click(screen.getByRole("button", { name: "Ablehnung bestätigen" }));
    await waitFor(() => expect(calls.find((c) => c.url.endsWith("/reject"))?.body).toEqual({ reason: "Falsche Nummer" }));
  });

  it("creates a manual request with the verbatim number", async () => {
    const calls = mockApi([]);
    const user = userEvent.setup();
    renderIntl(<LexofficeInvoiceCopyCard ticketId={TICKET} canUpdate canLinkContacts={false} />);
    expect(await screen.findByText("Keine Anfrage zu diesem Ticket.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rechnungskopie anfordern" }));
    await user.type(screen.getByLabelText("Rechnungsnummer"), "RE-1019");
    await user.click(screen.getByRole("button", { name: "Anfrage anlegen" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ invoice_number: "RE-1019" }));
  });

  it("stays hidden without tickets:update or when the list is not reachable", async () => {
    mockApi([request()], 403);
    const { container } = renderIntl(<LexofficeInvoiceCopyCard ticketId={TICKET} canUpdate canLinkContacts />);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
