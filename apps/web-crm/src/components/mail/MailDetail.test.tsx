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

  it("opens the reply draft inline below the message after Antworten (operator 27.09.2026)", async () => {
    const draft = makeMessage({ id: "d1", direction: "out", status: "draft", to_addresses: ["mieter@example.com"], subject: "AW: Heizung defekt", body: "Sehr geehrte Damen und Herren," });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/messages/m1/reply-draft") && init?.method === "POST") return jsonResponse(draft, 201);
      return jsonResponse([], 200);
    });
    const onCreated = vi.fn();
    renderIntl(<MailDetail message={makeMessage({})} canApprove={false} canReadMembers={false} onUpdated={() => {}} onCreated={onCreated} />);
    expect(screen.queryByTestId("mail-reply-draft")).not.toBeInTheDocument();
    await userEvent.click(within(screen.getByTestId("mail-actions-top")).getByRole("button", { name: "Antworten" }));
    const section = await screen.findByTestId("mail-reply-draft");
    expect(within(section).getByText("Antwortentwurf")).toBeInTheDocument();
    expect(within(section).getByLabelText("Text")).toHaveValue("Sehr geehrte Damen und Herren,");
    expect(within(section).getByLabelText("An (kommagetrennt)")).toHaveValue("mieter@example.com");
    expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ id: "d1" }));
    // The original message stays visible above the editor.
    expect(screen.getByTestId("mail-body")).toHaveTextContent("Voller Text");

    // A second click reopens the same draft instead of creating another one.
    await userEvent.click(within(screen.getByTestId("mail-actions-top")).getByRole("button", { name: "Antworten" }));
    expect(fetchMock.mock.calls.filter(([input, init]) => String(input).endsWith("/reply-draft") && init?.method === "POST")).toHaveLength(1);
  });

  it("asks the server for the reply draft instead of opening any draft of the thread (review 1.36.0)", async () => {
    // An older inbound mail of the thread with an abandoned draft addressed to its sender.
    const older = makeMessage({ id: "m0", from_address: "handwerker@example.com", received_at: "2026-09-10T08:00:00Z" });
    const stale = makeMessage({ id: "d0", direction: "out", status: "draft", to_addresses: ["handwerker@example.com"], body: "Alte Antwort zu Mail 1" });
    const draft = makeMessage({ id: "d2", direction: "out", status: "draft", to_addresses: ["mieter@example.com"], body: "Entwurf zu dieser Mail" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/messages/m1/thread")) return jsonResponse([older, stale, makeMessage({})], 200);
      if (url.endsWith("/messages/m1/reply-draft") && init?.method === "POST") return jsonResponse(draft, 200);
      if (url.endsWith("/messages/d2/draft") && init?.method === "PATCH") return jsonResponse(draft, 200);
      if (url.endsWith("/messages/d2/submit") && init?.method === "POST") return jsonResponse({ ...draft, status: "pending" }, 200);
      return jsonResponse([], 200);
    });
    renderIntl(<MailDetail message={makeMessage({})} canApprove={false} canReadMembers={false} onUpdated={() => {}} onCreated={() => {}} />);
    await screen.findByText("Verlauf");
    await userEvent.click(within(screen.getByTestId("mail-actions-top")).getByRole("button", { name: "Antworten" }));
    const section = await screen.findByTestId("mail-reply-draft");
    expect(within(section).getByLabelText("Text")).toHaveValue("Entwurf zu dieser Mail");
    expect(within(section).getByLabelText("An (kommagetrennt)")).toHaveValue("mieter@example.com");
    const replyPosts = fetchMock.mock.calls.filter(([input, init]) => String(input).endsWith("/messages/m1/reply-draft") && init?.method === "POST");
    expect(replyPosts).toHaveLength(1);
    expect(JSON.parse(String(replyPosts[0]?.[1]?.body))).toEqual({});
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/messages/d0/"))).toBe(false);
    await userEvent.click(within(section).getByRole("button", { name: "Zur Freigabe" }));
    expect(await screen.findByTestId("mail-reply-draft-status")).toHaveTextContent("zur Freigabe eingereicht");
  });

  it("shows an adopted suggestion in the open reply editor and submits it (review 1.36.0)", async () => {
    const template = makeMessage({ id: "d1", direction: "out", status: "draft", to_addresses: ["mieter@example.com"], body: "Guten Tag [Name]," });
    const adopted = { ...template, body: "Vielen Dank, der Techniker kommt am Montag.\n\n-- \nMax Muster" };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/messages/m1/reply-draft") && init?.method === "POST") {
        const sent = JSON.parse(String(init.body)) as { body?: string };
        return jsonResponse(sent.body ? adopted : template, 200);
      }
      if (url.endsWith("/messages/d1/draft") && init?.method === "PATCH") return jsonResponse({ ...template, body: JSON.parse(String(init.body)).body }, 200);
      if (url.endsWith("/messages/d1/submit") && init?.method === "POST") return jsonResponse({ ...adopted, status: "pending" }, 200);
      return jsonResponse([], 200);
    });
    const message = makeMessage({ suggestion_status: "ready", suggestion: { reply_draft: "Vielen Dank, der Techniker kommt am Montag." } });
    renderIntl(<MailDetail message={message} canApprove={false} canReadMembers={false} onUpdated={() => {}} onCreated={() => {}} />);
    await userEvent.click(within(screen.getByTestId("mail-actions-top")).getByRole("button", { name: "Antworten" }));
    const section = await screen.findByTestId("mail-reply-draft");
    expect(within(section).getByLabelText("Text")).toHaveValue("Guten Tag [Name],");

    // The server replaces the text of the same draft id; the open editor must show it.
    await userEvent.click(screen.getByRole("button", { name: "Vorschlag übernehmen" }));
    await waitFor(() => expect(within(section).getByLabelText("Text")).toHaveValue(adopted.body));
    await userEvent.click(within(section).getByRole("button", { name: "Zur Freigabe" }));
    expect(await screen.findByTestId("mail-reply-draft-status")).toHaveTextContent("zur Freigabe eingereicht");
    const patch = fetchMock.mock.calls.find(([input, init]) => String(input).endsWith("/messages/d1/draft") && init?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body)).body).toBe(adopted.body);
  });

  it("shows the server's reason when Antworten is refused", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/messages/m1/reply-draft") && init?.method === "POST") {
        return jsonResponse({ title: "Nicht gefunden", status: 404, detail: "Keine Berechtigung für das Postfach dieser Nachricht." }, 404);
      }
      return jsonResponse([], 200);
    });
    renderIntl(<MailDetail message={makeMessage({})} canApprove={false} canReadMembers={false} onUpdated={() => {}} onCreated={() => {}} />);
    await userEvent.click(within(screen.getByTestId("mail-actions-top")).getByRole("button", { name: "Antworten" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Keine Berechtigung für das Postfach dieser Nachricht.");
    expect(screen.queryByTestId("mail-reply-draft")).not.toBeInTheDocument();
  });
});
