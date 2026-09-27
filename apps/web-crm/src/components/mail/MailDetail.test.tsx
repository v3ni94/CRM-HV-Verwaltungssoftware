import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MailDetail } from "./MailDetail";
import type { Message } from "./MailWorkspace";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

function makeMessage(overrides: Partial<Message>): Message {
  return {
    id: "m1",
    channel: "email",
    direction: "in",
    status: "new",
    from_address: "mieter@example.com",
    to_addresses: [],
    subject: "Heizung defekt",
    body: "Voller Text",
    body_preview: "Voller Text",
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

describe("MailDetail", () => {
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([], 200));
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows a loading hint while only the list preview is known (M3)", () => {
    const row = makeMessage({});
    delete row.body;
    renderIntl(<MailDetail message={row} canApprove={false} canReadMembers={false} onUpdated={() => {}} onCreated={() => {}} />);
    expect(screen.getByText("Nachricht wird geladen...")).toBeInTheDocument();
    expect(screen.queryByTestId("mail-body")).not.toBeInTheDocument();
  });

  it("shows the Gmail archive outcome and offers a manual retry after a failure", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/api/bff/mail/messages/m1/archive") && init?.method === "POST") {
        return jsonResponse(makeMessage({ status: "done", archive_status: "archived", archived_at: "2026-09-27T09:00:00Z" }), 200);
      }
      return jsonResponse([], 200);
    });
    const onUpdated = vi.fn();
    renderIntl(
      <MailDetail
        message={makeMessage({ status: "done", archive_status: "failed", archive_error: "HTTP 500", archive_attempted_at: "2026-09-27T08:00:00Z" })}
        canApprove={false}
        canReadMembers={false}
        onUpdated={onUpdated}
        onCreated={() => {}}
      />,
    );
    const line = screen.getByTestId("mail-archive-status");
    expect(line.textContent).toContain("Archivierung in Gmail fehlgeschlagen");
    expect(line.textContent).toContain("HTTP 500");
    await userEvent.click(screen.getByRole("button", { name: "Archivierung jetzt nachholen" }));
    await waitFor(() => expect(onUpdated).toHaveBeenCalled());
    expect(onUpdated).toHaveBeenCalledWith(expect.objectContaining({ archive_status: "archived" }));
    expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/messages/m1/archive") && init?.method === "POST")).toBe(true);
  });

  it("shows the archived date for an archived mail without a retry", () => {
    renderIntl(
      <MailDetail
        message={makeMessage({ status: "done", archive_status: "archived", archived_at: "2026-09-27T09:00:00Z" })}
        canApprove={false}
        canReadMembers={false}
        onUpdated={() => {}}
        onCreated={() => {}}
      />,
    );
    expect(screen.getByTestId("mail-archive-status").textContent).toContain("In Gmail archiviert am");
    expect(screen.queryByRole("button", { name: "Archivierung jetzt nachholen" })).not.toBeInTheDocument();
  });

  it("lists attachments the intake refused (M8)", () => {
    renderIntl(
      <MailDetail
        message={makeMessage({
          classification: {
            attachments_rejected: [{ filename: "setup.exe", mime: "application/x-msdownload", size: 4, reason: "Dateityp nicht zulässig." }],
          },
        })}
        canApprove={false}
        canReadMembers={false}
        onUpdated={() => {}}
        onCreated={() => {}}
      />,
    );
    expect(screen.getByTestId("mail-attachments-rejected")).toHaveTextContent("setup.exe (Dateityp nicht zulässig.)");
    expect(screen.getByTestId("mail-body")).toHaveTextContent("Voller Text");
  });

  it("explains an open send attempt and lets an approver resume or reject it (M1)", () => {
    renderIntl(
      <MailDetail
        message={makeMessage({ direction: "out", status: "sending", to_addresses: ["mieter@example.com"] })}
        canApprove
        canReadMembers={false}
        onUpdated={() => {}}
        onCreated={() => {}}
      />,
    );
    expect(screen.getByTestId("mail-sending-hint")).toHaveTextContent("Versand noch ohne Nachweis");
    expect(screen.getByRole("button", { name: "Freigeben und senden" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ablehnen" })).toBeInTheDocument();
    expect(screen.getByText("wird gesendet")).toBeInTheDocument();
  });

  it("shows the action bar above and below the message body", () => {
    renderIntl(<MailDetail message={makeMessage({})} canApprove={false} canReadMembers={false} onUpdated={() => {}} onCreated={() => {}} />);
    const top = screen.getByTestId("mail-actions-top");
    const bottom = screen.getByTestId("mail-actions-bottom");
    expect(top).toHaveClass("sticky");
    for (const bar of [top, bottom]) {
      expect(within(bar).getByRole("button", { name: "Antworten" })).toBeInTheDocument();
      expect(within(bar).getByRole("button", { name: "Erledigt" })).toBeInTheDocument();
    }
    const body = screen.getByTestId("mail-body");
    expect(top.compareDocumentPosition(body) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
