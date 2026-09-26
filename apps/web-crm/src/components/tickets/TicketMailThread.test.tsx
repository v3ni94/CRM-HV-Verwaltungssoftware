import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { TicketMailThread, displayStatus, type ThreadMessage } from "./TicketMailThread";

const TICKET = "01920000-0000-7000-8000-00000000f404";
const DOC = "01920000-0000-7000-8000-0000000000d1";

const inbound: ThreadMessage = {
  id: "01920000-0000-7000-8000-0000000000a1",
  direction: "in",
  status: "assigned",
  from_address: "erika@example.com",
  to_addresses: ["info@example.com", "hans@example.com"],
  cc_addresses: ["hans@example.com"],
  subject: "Wasserschaden Küche",
  body: "Im Bad tropft es.\n\nAm 24.09.2026 schrieb Verwaltung:\n> alter Text",
  body_html: "<p>Im Bad <b>tropft</b> es.</p>",
  received_at: "2026-09-24T07:00:00Z",
  sent_at: null,
  mailbox_address: "info@example.com",
  rejection_note: null,
  send_error: null,
  attachments: [
    { document_id: DOC, filename: "foto.png", mime_type: "image/png", size: 2048, missing: false },
    { document_id: "01920000-0000-7000-8000-0000000000d2", filename: "liste.xlsx", mime_type: "application/vnd.ms-excel", size: 100, missing: false },
  ],
};
const outbound: ThreadMessage = {
  ...inbound,
  id: "01920000-0000-7000-8000-0000000000a2",
  direction: "out",
  status: "pending",
  from_address: null,
  to_addresses: ["erika@example.com"],
  cc_addresses: [],
  subject: "AW: Wasserschaden Küche TNR#412",
  body: "Wir kümmern uns.",
  body_html: null,
  received_at: null,
  sent_at: null,
  created_at: "2026-09-24T09:00:00Z",
  send_error: "SMTP-Versand fehlgeschlagen: TimeoutError",
  attachments: [],
};

describe("TicketMailThread", () => {
  it("renders inbound and outbound mails with status, addresses, attachments and preview", async () => {
    const onReply = vi.fn();
    renderIntl(<TicketMailThread ticketId={TICKET} messages={[inbound, outbound]} canReply onReply={onReply} />);
    const entries = screen.getAllByRole("listitem").filter((li) => li.dataset.testid?.startsWith("ticket-mail-"));
    expect(screen.getByTestId("ticket-mail-in")).toBeInTheDocument();
    expect(screen.getByTestId("ticket-mail-out")).toBeInTheDocument();
    expect(entries.length).toBeGreaterThanOrEqual(2);

    const first = screen.getByTestId("ticket-mail-in");
    expect(within(first).getByText("Eingang")).toBeInTheDocument();
    expect(within(first).getByText("zugeordnet")).toBeInTheDocument();
    expect(within(first).getByText("24.09.2026 09:00")).toBeInTheDocument();
    expect(within(first).getByText(/Von: erika@example.com/)).toBeInTheDocument();
    expect(within(first).getByText(/Kopie: hans@example.com/)).toBeInTheDocument();
    // HTML mails render sanitised HTML by default; the text view folds the quote.
    expect(within(first).getByTestId("ticket-mail-html").innerHTML).toContain("<b>tropft</b>");
    await userEvent.click(within(first).getByRole("button", { name: "Als Text anzeigen" }));
    expect(within(first).getByTestId("ticket-mail-text")).toHaveTextContent("Im Bad tropft es.");
    expect(within(first).getByTestId("ticket-mail-text")).not.toHaveTextContent("alter Text");
    await userEvent.click(within(first).getByRole("button", { name: "Zitierten Text anzeigen" }));
    expect(within(first).getByTestId("ticket-mail-text")).toHaveTextContent("alter Text");

    // Attachments: name, size, type; preview only for images and PDF; download for all.
    const rows = within(first).getAllByTestId("ticket-mail-attachment");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByText("foto.png")).toBeInTheDocument();
    expect(within(rows[0]!).getByText(/2,0 KB · image\/png/)).toBeInTheDocument();
    expect(within(rows[0]!).getByRole("link", { name: "Herunterladen" })).toHaveAttribute(
      "href",
      `/api/bff/tickets/${TICKET}/mail-attachments/${DOC}/content?download=true`,
    );
    expect(within(rows[0]!).getByRole("button", { name: /Als Beleg erfassen/ })).toBeInTheDocument();
    expect(within(rows[1]!).queryByRole("button", { name: "Vorschau" })).not.toBeInTheDocument();
    await userEvent.click(within(rows[0]!).getByRole("button", { name: "Vorschau" }));
    expect(within(rows[0]!).getByRole("img", { name: "foto.png" })).toHaveAttribute("src", `/api/bff/tickets/${TICKET}/mail-attachments/${DOC}/content`);

    const second = screen.getByTestId("ticket-mail-out");
    expect(within(second).getByText("Ausgang")).toBeInTheDocument();
    expect(within(second).getByText("fehlgeschlagen")).toBeInTheDocument();
    expect(within(second).getByRole("alert")).toHaveTextContent("TimeoutError");
    expect(within(second).getByText(/Von: info@example.com/)).toBeInTheDocument();

    await userEvent.click(within(first).getByRole("button", { name: "Auf diese Mail antworten" }));
    expect(onReply).toHaveBeenCalledWith(inbound);
  });

  it("maps statuses and hides reply without permission", () => {
    expect(displayStatus(outbound)).toBe("failed");
    expect(displayStatus({ ...outbound, send_error: null })).toBe("pending");
    expect(displayStatus({ ...outbound, status: "sent" })).toBe("sent");
    renderIntl(<TicketMailThread ticketId={TICKET} messages={[inbound]} canReply={false} />);
    expect(screen.queryByRole("button", { name: "Auf diese Mail antworten" })).not.toBeInTheDocument();
  });

  it("shows an empty hint", () => {
    renderIntl(<TicketMailThread ticketId={TICKET} messages={[]} canReply />);
    expect(screen.getByText("Zu diesem Ticket liegen keine E-Mails vor.")).toBeInTheDocument();
  });

  it("shows who drafted and who approved an outbound reply (M20-03)", () => {
    const flagged: ThreadMessage = {
      ...outbound,
      id: "01920000-0000-7000-8000-0000000000a3",
      status: "sent",
      send_error: null,
      sent_at: "2026-09-25T08:00:00Z",
      created_by_name: "Azubi Anna",
      approved_by_name: "Chefin Clara",
      approved_at: "2026-09-25T07:55:00Z",
      author_approval_required: true,
      author_approval_reason: "azubi",
    };
    const direct: ThreadMessage = {
      ...flagged,
      id: "01920000-0000-7000-8000-0000000000a4",
      created_by_name: "Chefin Clara",
      author_approval_required: false,
      author_approval_reason: null,
    };
    const waiting: ThreadMessage = { ...flagged, id: "01920000-0000-7000-8000-0000000000a5", status: "pending", approved_by_name: null, approved_at: null };
    renderIntl(<TicketMailThread ticketId={TICKET} messages={[flagged, direct, waiting]} canReply={false} />);
    const traces = screen.getAllByTestId("ticket-mail-trace");
    expect(traces[0]).toHaveTextContent("Vorformuliert von Azubi Anna am 24.09.2026 11:00 (Freigabepflicht: Azubi), freigegeben von Chefin Clara am 25.09.2026 09:55");
    expect(traces[1]).toHaveTextContent("Vorformuliert von Chefin Clara am 24.09.2026 11:00, selbst freigegeben am 25.09.2026 09:55");
    expect(traces[2]).toHaveTextContent("wartet auf Freigabe durch eine zweite Person");
  });
});
