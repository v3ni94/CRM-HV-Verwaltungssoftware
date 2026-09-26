import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketReplyPanel } from "./TicketReplyPanel";

const TICKET = "01920000-0000-7000-8000-00000000f404";
const TEMPLATE = "01920000-0000-7000-8000-0000000000e1";
const DOC = "01920000-0000-7000-8000-0000000000d1";

const templates = [{ id: TEMPLATE, name: "Eingangsbestätigung", topic: "vertrag" }];
type Preview = {
  template_id: string;
  template_name: string;
  subject: string;
  body: string;
  to_addresses: string[];
  mailbox_id: string | null;
  mailbox_address: string | null;
  can_send: boolean;
  attachments: { document_id: string; title: string | null; filename: string | null; missing: boolean }[];
};
const preview: Preview = {
  template_id: TEMPLATE,
  template_name: "Eingangsbestätigung",
  subject: "AW: Ticket 404",
  body: "Sehr geehrte Frau Muster,\n\nvielen Dank für Ihre Nachricht.",
  to_addresses: ["erika@example.com"],
  mailbox_id: "01920000-0000-7000-8000-0000000000b1",
  mailbox_address: "info@example.com",
  can_send: true,
  attachments: [{ document_id: DOC, title: "Merkblatt", filename: "merkblatt.pdf", missing: false }],
};

function mockApi(overrides: Partial<Preview> = {}) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.includes("/reply-templates?active=true")) return jsonResponse(templates);
    if (url.includes("/preview")) return jsonResponse({ ...preview, ...overrides });
    if (url.endsWith(`/tickets/${TICKET}/reply`)) return jsonResponse({ id: "m1", status: "pending" }, 201);
    return jsonResponse({ title: "unerwartet" }, 500);
  });
  return calls;
}

describe("TicketReplyPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the filled preview, allows edits and sends only after the explicit click", async () => {
    const calls = mockApi();
    renderIntl(<TicketReplyPanel ticketId={TICKET} canSend />);
    await waitFor(() => expect(screen.getByRole("option", { name: "Eingangsbestätigung" })).toBeInTheDocument());
    expect(calls.some((c) => c.url.endsWith("/reply"))).toBe(false);

    await userEvent.selectOptions(screen.getByLabelText("Antwortvorlage wählen"), TEMPLATE);
    await waitFor(() => expect(screen.getByTestId("ticket-reply-preview")).toBeInTheDocument());
    expect(screen.getByLabelText("Betreff")).toHaveValue("AW: Ticket 404");
    expect(screen.getByLabelText("Text")).toHaveValue(preview.body);
    expect(screen.getByLabelText("An")).toHaveValue("erika@example.com");
    expect(screen.getByText("info@example.com")).toBeInTheDocument();
    expect(within(screen.getByTestId("ticket-reply-attachments")).getByText("Merkblatt")).toBeInTheDocument();
    // Vorschau allein sendet nichts.
    expect(calls.some((c) => c.url.endsWith("/reply"))).toBe(false);

    await userEvent.type(screen.getByLabelText("Text"), "\n\nMit freundlichen Grüßen");
    await userEvent.click(screen.getByRole("button", { name: "Antwort senden" }));
    await waitFor(() => expect(screen.getByTestId("ticket-reply-sent")).toBeInTheDocument());
    const sendCall = calls.find((c) => c.url.endsWith("/reply"));
    expect(sendCall?.init?.method).toBe("POST");
    const payload = JSON.parse(String(sendCall?.init?.body)) as Record<string, unknown>;
    expect(payload.confirm).toBe(true);
    expect(payload.template_id).toBe(TEMPLATE);
    expect(payload.attachment_document_ids).toEqual([DOC]);
    expect(String(payload.body)).toContain("Mit freundlichen Grüßen");
    expect(payload.to_addresses).toEqual(["erika@example.com"]);
  });

  it("blocks sending while placeholders are open or no mailbox is configured", async () => {
    mockApi({ body: "{anrede},\n\nText mit {unbekannt}.", can_send: false, mailbox_address: null });
    renderIntl(<TicketReplyPanel ticketId={TICKET} canSend />);
    await waitFor(() => expect(screen.getByRole("option", { name: "Eingangsbestätigung" })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Antwortvorlage wählen"), TEMPLATE);
    await waitFor(() => expect(screen.getByTestId("ticket-reply-preview")).toBeInTheDocument());
    expect(screen.getByText("Der Text enthält noch offene Platzhalter.")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("kein sendefähiges Postfach");
    expect(screen.getByRole("button", { name: "Antwort senden" })).toBeDisabled();
  });

  it("hides the send button without permission", async () => {
    mockApi();
    renderIntl(<TicketReplyPanel ticketId={TICKET} canSend={false} />);
    await waitFor(() => expect(screen.getByRole("option", { name: "Eingangsbestätigung" })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Antwortvorlage wählen"), TEMPLATE);
    await waitFor(() => expect(screen.getByTestId("ticket-reply-preview")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Antwort senden" })).not.toBeInTheDocument();
  });
});
