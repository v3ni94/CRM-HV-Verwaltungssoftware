import { screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MailWorkspace } from "./MailWorkspace";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const listRow = {
  id: "m1",
  channel: "email",
  direction: "in",
  status: "new",
  from_address: "mieter@example.com",
  to_addresses: [],
  subject: "Heizung defekt",
  body_preview: "Nur die Vorschau",
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
};

describe("MailWorkspace", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the list without text, the selected message in full and the pending count (M3)", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url.startsWith("/api/bff/mail/messages/count")) return jsonResponse({ count: 7 }, 200);
      if (url === "/api/bff/mail/messages/m1") return jsonResponse({ ...listRow, body: "Der vollständige Text", body_html: null }, 200);
      if (url === "/api/bff/mail/messages/m1/thread") return jsonResponse([], 200);
      if (url.startsWith("/api/bff/mail/messages?")) return jsonResponse([listRow], 200);
      if (url === "/api/bff/mail/mailboxes") return jsonResponse([], 200);
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(<MailWorkspace canApprove canReadMembers={false} />);

    await waitFor(() => expect(screen.getByTestId("mail-body")).toHaveTextContent("Der vollständige Text"));
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(calls.some((u) => u.startsWith("/api/bff/mail/messages/count?direction=out&status=pending"))).toBe(true);
    // The badge never loads the pending list itself.
    expect(calls.filter((u) => u.startsWith("/api/bff/mail/messages?direction=out&status=pending")).length).toBe(0);
  });
});
