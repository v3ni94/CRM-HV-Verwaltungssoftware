import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketReplyPanel } from "./TicketReplyPanel";

const TICKET = "01920000-0000-7000-8000-00000000f404";
const TEMPLATE = "01920000-0000-7000-8000-0000000000e1";
const DOC = "01920000-0000-7000-8000-0000000000d1";
const MSG = "01920000-0000-7000-8000-0000000000a1";

const templates = [{ id: TEMPLATE, name: "Eingangsbestätigung", topic: "vertrag" }];
const context = {
  reply_to_message_id: MSG,
  subject: "AW: Wasserschaden Küche TNR#412",
  to_addresses: ["erika@example.com"],
  cc_addresses: ["hans@example.com"],
  unverified_sender: null as string | null,
  mailbox_id: "01920000-0000-7000-8000-0000000000b1",
  mailbox_address: "info@example.com",
  can_send: true,
  tnr: "TNR#412",
};
const preview = {
  ...context,
  template_id: TEMPLATE,
  template_name: "Eingangsbestätigung",
  subject: "AW: Ticket 412 TNR#412",
  body: "Sehr geehrte Frau Muster,\n\nvielen Dank für Ihre Nachricht.",
  attachments: [{ document_id: DOC, title: "Merkblatt", filename: "merkblatt.pdf", missing: false }],
};

function mockApi(ctx: Partial<{ [K in keyof typeof context]: (typeof context)[K] | null }> = {}, pv: Partial<typeof preview> = {}) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.includes("/reply-templates?active=true")) return jsonResponse(templates);
    if (url.includes("/reply-context")) return jsonResponse({ ...context, ...ctx });
    if (url.includes("/preview")) return jsonResponse({ ...preview, ...pv });
    if (url.includes("/reply-documents?q=")) return jsonResponse([{ document_id: DOC, title: "Hausordnung", filename: "hausordnung.pdf", mime_type: "application/pdf", size: 4096 }]);
    if (url.endsWith("/documents")) return jsonResponse({ id: "01920000-0000-7000-8000-0000000000d9", title: "upload.pdf", filename: "upload.pdf", size: 10 }, 201);
    if (url.endsWith(`/tickets/${TICKET}/reply`)) return jsonResponse({ id: "m1", status: "pending" }, 201);
    return jsonResponse({ title: "unerwartet" }, 500);
  });
  return calls;
}

describe("TicketReplyPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("prefills recipients, cc and subject with TNR and sends a free text reply only after the click", async () => {
    const calls = mockApi();
    const onSent = vi.fn();
    renderIntl(<TicketReplyPanel ticketId={TICKET} canSend target={{ messageId: MSG, at: "2026-09-24T07:00:00Z" }} onSent={onSent} />);
    await waitFor(() => expect(screen.getByTestId("ticket-reply-form")).toBeInTheDocument());
    expect(screen.getByTestId("ticket-reply-target")).toHaveTextContent("24.09.2026 09:00");
    expect(screen.getByLabelText("An")).toHaveValue("erika@example.com");
    expect(screen.getByLabelText("Kopie")).toHaveValue("hans@example.com");
    expect(screen.getByLabelText("Betreff")).toHaveValue("AW: Wasserschaden Küche TNR#412");
    expect(screen.getByText(/Kennung TNR#412/)).toBeInTheDocument();
    expect(calls.some((c) => c.url.includes(`reply_to_message_id=${MSG}`))).toBe(true);
    // Leerer Text: kein Versand möglich.
    expect(screen.getByRole("button", { name: "Antwort senden" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Text"), "Wir kümmern uns.");
    expect(calls.some((c) => c.url.endsWith("/reply"))).toBe(false);

    // Eigener Anhang aus der Dokumentsuche.
    await userEvent.type(screen.getByLabelText("Dokument suchen"), "haus{enter}");
    await waitFor(() => expect(screen.getByTestId("ticket-reply-document-hits")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Hinzufügen: Hausordnung" }));
    expect(within(screen.getByTestId("ticket-reply-attachments")).getByText(/Hausordnung/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Antwort senden" }));
    await waitFor(() => expect(screen.getByTestId("ticket-reply-sent")).toBeInTheDocument());
    const sendCall = calls.find((c) => c.url.endsWith("/reply"));
    expect(sendCall?.init?.method).toBe("POST");
    const payload = JSON.parse(String(sendCall?.init?.body)) as Record<string, unknown>;
    expect(payload.confirm).toBe(true);
    expect(payload.template_id).toBeNull();
    expect(payload.to_addresses).toEqual(["erika@example.com"]);
    expect(payload.cc_addresses).toEqual(["hans@example.com"]);
    expect(payload.reply_to_message_id).toBe(MSG);
    expect(payload.subject).toBe("AW: Wasserschaden Küche TNR#412");
    expect(payload.attachment_document_ids).toEqual([DOC]);
    expect(onSent).toHaveBeenCalledWith({ id: "m1", status: "pending" });
  });

  it("fills subject, text and attachments from a template and keeps them editable", async () => {
    const calls = mockApi();
    renderIntl(<TicketReplyPanel ticketId={TICKET} canSend />);
    await waitFor(() => expect(screen.getByRole("option", { name: "Eingangsbestätigung" })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Antwortvorlage wählen"), TEMPLATE);
    await waitFor(() => expect(screen.getByTestId("ticket-reply-preview")).toBeInTheDocument());
    expect(screen.getByLabelText("Betreff")).toHaveValue("AW: Ticket 412 TNR#412");
    expect(screen.getByLabelText("Text")).toHaveValue(preview.body);
    expect(within(screen.getByTestId("ticket-reply-attachments")).getByText("Merkblatt")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Text"), "\n\nMit freundlichen Grüßen");
    await userEvent.click(screen.getByRole("button", { name: "Antwort senden" }));
    await waitFor(() => expect(screen.getByTestId("ticket-reply-sent")).toBeInTheDocument());
    const payload = JSON.parse(String(calls.find((c) => c.url.endsWith("/reply"))?.init?.body)) as Record<string, unknown>;
    expect(payload.template_id).toBe(TEMPLATE);
    expect(payload.attachment_document_ids).toEqual([DOC]);
    expect(String(payload.body)).toContain("Mit freundlichen Grüßen");
  });

  it("never takes an unverified sender as recipient without explicit choice", async () => {
    mockApi({ to_addresses: ["erika@example.com"], cc_addresses: [], unverified_sender: "fremd@example.com" });
    renderIntl(<TicketReplyPanel ticketId={TICKET} canSend />);
    await waitFor(() => expect(screen.getByTestId("ticket-reply-unverified")).toBeInTheDocument());
    expect(screen.getByLabelText("An")).toHaveValue("erika@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Als Empfänger übernehmen" }));
    expect(screen.getByLabelText("An")).toHaveValue("fremd@example.com");
  });

  it("blocks sending on open placeholders, invalid addresses or missing mailbox", async () => {
    mockApi({ can_send: false, mailbox_address: null }, { body: "{anrede},\n\nText mit {unbekannt}." });
    renderIntl(<TicketReplyPanel ticketId={TICKET} canSend />);
    await waitFor(() => expect(screen.getByRole("option", { name: "Eingangsbestätigung" })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Antwortvorlage wählen"), TEMPLATE);
    await waitFor(() => expect(screen.getByText("Der Text enthält noch offene Platzhalter.")).toBeInTheDocument());
    expect(screen.getByRole("alert")).toHaveTextContent("kein sendefähiges Postfach");
    expect(screen.getByRole("button", { name: "Antwort senden" })).toBeDisabled();
    await userEvent.clear(screen.getByLabelText("Kopie"));
    await userEvent.type(screen.getByLabelText("Kopie"), "kein mail");
    expect(screen.getByText("Ungültige E-Mail-Adresse: kein mail")).toBeInTheDocument();
  });

  it("hides the send button without permission", async () => {
    mockApi();
    renderIntl(<TicketReplyPanel ticketId={TICKET} canSend={false} />);
    await waitFor(() => expect(screen.getByTestId("ticket-reply-form")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Antwort senden" })).not.toBeInTheDocument();
  });
});
