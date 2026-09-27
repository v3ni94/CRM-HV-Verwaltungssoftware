import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

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

  it("marks mails in progress yellow with the handler's name under the timestamp", () => {
    const messages = [
      makeMessage({ id: "m1", subject: "Offen" }),
      makeMessage({
        id: "m2",
        subject: "In Arbeit",
        in_progress: true,
        handler_display_name: "Ina Brink",
      }),
      makeMessage({ id: "m3", subject: "Ohne Namen", in_progress: true, handler_display_name: null }),
    ];
    renderIntl(<MailList messages={messages} selectedId={null} onSelect={() => {}} loading={false} />);
    const label = screen.getByText("Ina Brink");
    expect(label).toHaveAttribute("title", "In Bearbeitung von Ina Brink");
    const row = screen.getByText("In Arbeit").closest("button");
    expect(row?.className).toContain("bg-progress-bg");
    expect(screen.getByText("Offen").closest("button")?.className).not.toContain("bg-progress-bg");
    expect(screen.getByText("Offen").closest("li")).not.toHaveAttribute("data-in-progress");
    expect(screen.getByText("In Arbeit").closest("li")).toHaveAttribute("data-in-progress", "true");
    // Ohne Bearbeiternamen bleibt die Kennzeichnung mit neutralem Text.
    expect(screen.getAllByTestId("mail-handler")).toHaveLength(2);
    expect(screen.getByText("In Bearbeitung")).toBeInTheDocument();
  });

  it("shows a duplicate badge for a linked copy from another mailbox", () => {
    renderIntl(
      <MailList
        messages={[makeMessage({ id: "m1", duplicate_of_id: "m0" })]}
        selectedId={null}
        onSelect={() => {}}
        loading={false}
      />,
    );
    expect(screen.getByText("Duplikat")).toBeInTheDocument();
  });

  const three = () => [
    makeMessage({ id: "m1", subject: "Erste" }),
    makeMessage({ id: "m2", subject: "Zweite" }),
    makeMessage({ id: "m3", subject: "Dritte" }),
  ];

  it("toggles rows with Ctrl or Cmd click without opening them and clears on Escape", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    renderIntl(<MailList messages={three()} selectedId={null} onSelect={onSelect} loading={false} />);
    await user.keyboard("{Control>}");
    await user.click(screen.getByText("Erste"));
    await user.click(screen.getByText("Dritte"));
    await user.keyboard("{/Control}");
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByTestId("mail-bulk-bar")).toHaveTextContent("2 ausgewählt");
    await user.keyboard("{Meta>}");
    await user.click(screen.getByText("Erste"));
    await user.keyboard("{/Meta}");
    expect(screen.getByTestId("mail-bulk-bar")).toHaveTextContent("1 ausgewählt");
    await user.keyboard("{Escape}");
    expect(screen.queryByTestId("mail-bulk-bar")).not.toBeInTheDocument();
  });

  it("selects a range with Shift click from the last clicked row", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    renderIntl(<MailList messages={three()} selectedId={null} onSelect={onSelect} loading={false} />);
    await user.click(screen.getByText("Erste"));
    expect(onSelect).toHaveBeenCalledWith("m1");
    await user.keyboard("{Shift>}");
    await user.click(screen.getByText("Dritte"));
    await user.keyboard("{/Shift}");
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("mail-bulk-bar")).toHaveTextContent("3 ausgewählt");
  });

  it("selects all via the header checkbox and marks the selection done in one bulk call", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => jsonResponse({ changed: ["m1", "m2", "m3"], failed: [] }, 200));
    const onBulkChanged = vi.fn();
    const user = userEvent.setup();
    renderIntl(
      <MailList messages={three()} selectedId={null} onSelect={() => {}} loading={false} onBulkChanged={onBulkChanged} />,
    );
    await user.click(screen.getByRole("checkbox", { name: "Alle auswählen" }));
    expect(screen.getByTestId("mail-bulk-bar")).toHaveTextContent("3 ausgewählt");
    await user.click(screen.getByRole("button", { name: "Als erledigt markieren" }));
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(String(url)).toContain("/api/bff/mail/messages/bulk");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ ids: ["m1", "m2", "m3"], action: "done" });
    expect(onBulkChanged).toHaveBeenCalledWith(["m1", "m2", "m3"]);
    expect(screen.queryByTestId("mail-bulk-bar")).not.toBeInTheDocument();
    fetchSpy.mockRestore();
  });
});
