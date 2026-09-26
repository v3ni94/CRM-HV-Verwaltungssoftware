import { screen } from "@testing-library/react";

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
});
