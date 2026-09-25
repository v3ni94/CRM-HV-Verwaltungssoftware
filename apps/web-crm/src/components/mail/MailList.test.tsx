import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { MailList } from "./MailList";
import type { Message } from "./MailWorkspace";

function makeMessage(overrides: Partial<Message>): Message {
  return {
    id: "m1",
    channel: "email",
    direction: "in",
    status: "new",
    from_address: "mieter@example.com",
    to_addresses: [],
    subject: "Heizung defekt",
    body: "Text",
    received_at: "2026-09-20T08:00:00Z",
    sent_at: null,
    contact_id: null,
    property_id: null,
    ticket_id: null,
    thread_id: null,
    document_id: null,
    attachment_document_ids: [],
    classification: {},
    appointment_suggestions: [],
    created_by: null,
    mailbox_id: null,
    submitted_by: null,
    submitted_at: null,
    approved_by: null,
    approved_at: null,
    rejection_note: null,
    suggestion: {},
    suggestion_status: "none",
    ...overrides,
  };
}

describe("MailList", () => {
  it("shows an empty hint when there are no messages", () => {
    renderIntl(<MailList messages={[]} selectedId={null} onSelect={() => {}} loading={false} />);
    expect(screen.getByText("Keine Nachrichten.")).toBeInTheDocument();
  });

  it("lists messages with sender, subject and ticket badge, and reports selection", async () => {
    const onSelect = vi.fn();
    const messages = [
      makeMessage({ id: "m1" }),
      makeMessage({
        id: "m2",
        from_address: "eigentuemer@example.com",
        subject: "Kautionsrückzahlung",
        ticket_id: "t1",
        status: "assigned",
      }),
    ];
    renderIntl(<MailList messages={messages} selectedId="m1" onSelect={onSelect} loading={false} />);
    expect(screen.getByText("mieter@example.com")).toBeInTheDocument();
    expect(screen.getByText("Kautionsrückzahlung")).toBeInTheDocument();
    expect(screen.getByText("Ticket")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Kautionsrückzahlung"));
    expect(onSelect).toHaveBeenCalledWith("m2");
  });
});
