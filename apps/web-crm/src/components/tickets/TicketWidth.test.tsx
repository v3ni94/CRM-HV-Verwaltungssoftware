/** Darstellungsfehler Ticket #404 (operator 26.09.2026): lange Mailzeilen ohne Umbruch (URLs,
 *  Betreff) dürfen die Seite nicht verbreitern. Prüft die Umbruchklassen der Ticketliste, der
 *  Mailanzeige und der SafeText-Container bei sehr langen Zeichenketten (Handybreite). */
import { render, screen, within } from "@testing-library/react";

import { MailDetail } from "@/components/mail/MailDetail";
import type { Message } from "@/components/mail/MailWorkspace";
import { SafeHtml, SafeLine, SafeText } from "@/components/ui/SafeText";
import { renderIntl } from "@/test/intl";

import { TicketsList } from "./TicketsList";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

const LONG_URL = "https://example.invalid/pfad/" + "sehr-lange-zeichenkette-ohne-leerzeichen-".repeat(12);
const LONG_SUBJECT = "Betreff" + "X".repeat(400);

function expectWrapClasses(el: HTMLElement) {
  expect(el.className).toContain("break-words");
  expect(el.className).toContain("[overflow-wrap:anywhere]");
  expect(el.className).toContain("min-w-0");
}

describe("width safety of ticket and mail views", () => {
  beforeEach(() => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 360 });
  });

  it("SafeText keeps line breaks and breaks long lines anywhere", () => {
    render(
      <SafeText testId="body">
        {"Zeile 1\n" + LONG_URL}
      </SafeText>,
    );
    const el = screen.getByTestId("body");
    expectWrapClasses(el);
    expect(el.className).toContain("whitespace-pre-wrap");
    expect(el.textContent).toContain(LONG_URL);
  });

  it("SafeLine and SafeHtml constrain width", () => {
    render(
      <>
        <SafeLine testId="line">{LONG_SUBJECT}</SafeLine>
        <SafeHtml testId="html" html={`<table><tr><td>${LONG_URL}</td></tr></table><pre>${LONG_URL}</pre>`} />
      </>,
    );
    expectWrapClasses(screen.getByTestId("line"));
    const html = screen.getByTestId("html");
    expect(html.className).toContain("overflow-x-auto");
    expect(html.className).toContain("[&_table]:max-w-full");
    expect(html.className).toContain("[&_pre]:whitespace-pre-wrap");
    expect(html.querySelector("table")).not.toBeNull();
  });

  it("ticket list truncates the subject column and wraps the card title", () => {
    renderIntl(
      <TicketsList
        canApprove={false}
        initialTickets={[
          {
            id: "01920000-0000-7000-8000-00000000f404",
            number: 404,
            title: LONG_SUBJECT + " " + LONG_URL,
            priority: "normal",
            status: "new",
            sla_due_at: null,
            sla_breached: false,
          },
        ]}
      />,
    );
    const table = screen.getByRole("table");
    const titleLink = within(table).getByRole("link", { name: new RegExp(LONG_SUBJECT.slice(0, 20)) });
    expect(titleLink.className).toContain("truncate");
    expect(titleLink.className).toContain("max-w-full");
    expect(titleLink).toHaveAttribute("href", "/tickets/01920000-0000-7000-8000-00000000f404");
    const card = screen.getByTestId("ticket-card");
    const cardTitle = within(card).getByText(
      (_, el) => el?.tagName === "SPAN" && el.className.includes("font-medium") && (el.textContent ?? "").startsWith("#404"),
    );
    expect(cardTitle.className).toContain("break-words");
    expect(cardTitle.className).toContain("[overflow-wrap:anywhere]");
  });

  it("mail detail wraps subject, sender and body of a long mail", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("[]", { status: 200, headers: { "content-type": "application/json" } }));
    const message = {
      id: "01920000-0000-7000-8000-0000000000m1",
      channel: "email",
      direction: "in",
      status: "new",
      from_address: "absender-mit-sehr-langer-adresse-" + "x".repeat(200) + "@example.invalid",
      to_addresses: [],
      subject: LONG_SUBJECT,
      body: LONG_URL + "\n" + LONG_URL,
      received_at: "2026-09-25T08:00:00Z",
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
      gmail_message_id: null,
      suggestion: {},
      suggestion_status: "none",
    } as unknown as Message;
    renderIntl(<MailDetail message={message} canApprove={false} canReadMembers={false} onUpdated={() => undefined} onCreated={() => undefined} />);
    const heading = await screen.findByRole("heading", { level: 2 });
    expectWrapClasses(heading);
    const body = screen.getByTestId("mail-body");
    expectWrapClasses(body);
    expect(body.className).toContain("whitespace-pre-wrap");
    vi.restoreAllMocks();
  });
});
