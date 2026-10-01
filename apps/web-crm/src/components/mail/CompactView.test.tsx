import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CollapsibleBody, CompactView, type CompactData } from "./CompactView";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const DATA: CompactData = {
  message_id: "m1",
  thread_count: 2,
  summary: { source: "excerpt", text: "Die Heizung ist ausgefallen.", open_points: [], model: null },
  crm: {
    contact: { id: "c1", display_name: "Erika Muster" },
    property: { id: "p1", number: "801", name: "Posthaus" },
    open_tickets: { count: 1, items: [{ id: "t1", number: 42, title: "Heizung", status: "new" }] },
    open_items: { count: 2, overdue: 1, remaining: "1234.50" },
    recent: [],
  },
  reply: { source: "template", text: "Sehr geehrte Frau Muster,\n\nvielen Dank." },
  can_reply: true,
  body_long: false,
};

describe("CompactView", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows excerpt, CRM hint and reply proposal", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(DATA, 200));
    renderIntl(<CompactView messageId="m1" canUpdate />);
    expect(await screen.findByTestId("mail-compact-summary")).toHaveTextContent("Die Heizung ist ausgefallen.");
    expect(screen.getByText("Auszug der ersten Sätze")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Erika Muster" })).toHaveAttribute("href", "/contacts/c1");
    expect(screen.getByRole("link", { name: "#42" })).toBeInTheDocument();
    expect(screen.getByTestId("mail-compact-crm")).toHaveTextContent("1.234,50");
    expect(screen.getByRole("textbox", { name: "Antwortvorschlag" })).toHaveValue("Sehr geehrte Frau Muster,\n\nvielen Dank.");
  });

  it("Kurz senden creates the draft and submits it through the approval path", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.endsWith("/compact")) return jsonResponse(DATA, 200);
      if (url.endsWith("/reply-draft")) return jsonResponse({ id: "d1", status: "draft" }, 201);
      if (url.endsWith("/d1/submit")) return jsonResponse({ id: "d1", status: "pending" }, 200);
      return jsonResponse({}, 404);
    });
    const onDraft = vi.fn();
    renderIntl(<CompactView messageId="m1" canUpdate onDraftCreated={onDraft} />);
    await userEvent.click(await screen.findByRole("button", { name: "Kurz senden" }));
    await waitFor(() => expect(onDraft).toHaveBeenCalledWith({ id: "d1", status: "pending" }));
    expect(calls).toEqual([
      "GET /api/bff/mail/messages/m1/compact",
      "POST /api/bff/mail/messages/m1/reply-draft",
      "POST /api/bff/mail/messages/d1/submit",
    ]);
    expect(screen.getByRole("status")).toHaveTextContent("Antwort zur Freigabe eingereicht.");
  });

  it("AI reply draft needs approval before Kurz senden (T12)", async () => {
    const calls: string[] = [];
    let approved = false;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.endsWith("/compact")) {
        return jsonResponse(
          calls.length > 1
            ? { ...DATA, reply: { source: "reply_task", text: "KI Text", approved, draft: { tone: "sachlich", style_tone: "sachlich", placeholders: [], unknown_placeholders: [], open_questions: ["Termin"] } } }
            : DATA,
          200,
        );
      }
      if (url.endsWith("/reply-ai")) return jsonResponse({ status: "ready" }, 200);
      if (url.endsWith("/reply-ai/approve")) {
        approved = true;
        return jsonResponse({ approved: true }, 200);
      }
      return jsonResponse({}, 404);
    });
    renderIntl(<CompactView messageId="m1" canUpdate />);
    await userEvent.click(await screen.findByRole("button", { name: "Antwortentwurf (KI)" }));
    expect(await screen.findByRole("button", { name: "Entwurf freigeben" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Kurz senden" })).toBeDisabled();
    expect(screen.getByTestId("reply-draft-meta")).toHaveTextContent("Termin");
    await userEvent.click(screen.getByRole("button", { name: "Entwurf freigeben" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Kurz senden" })).toBeEnabled());
  });

  it("keeps the excerpt when no AI provider is released", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input).endsWith("/compact/summary") ? jsonResponse({ status: "skipped" }, 200) : jsonResponse(DATA, 200),
    );
    renderIntl(<CompactView messageId="m1" canUpdate />);
    await userEvent.click(await screen.findByRole("button", { name: "Mit KI zusammenfassen" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Kein freigegebener KI-Anbieter");
    expect(screen.getByTestId("mail-compact-summary")).toHaveTextContent("Die Heizung ist ausgefallen.");
  });

  it("hides send and summarize without update right", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(DATA, 200));
    renderIntl(<CompactView messageId="m1" canUpdate={false} />);
    await screen.findByTestId("mail-compact");
    expect(screen.queryByRole("button", { name: "Kurz senden" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mit KI zusammenfassen" })).not.toBeInTheDocument();
  });
});

describe("CollapsibleBody", () => {
  it("folds long text behind Vollständig anzeigen", async () => {
    const text = "Satz. ".repeat(200);
    renderIntl(<CollapsibleBody text={text} limit={50}>{(shown) => <div data-testid="b">{shown}</div>}</CollapsibleBody>);
    expect(screen.getByTestId("b").textContent!.length).toBeLessThan(60);
    await userEvent.click(screen.getByRole("button", { name: "Vollständig anzeigen" }));
    expect(screen.getByTestId("b").textContent).toBe(text);
  });
});
