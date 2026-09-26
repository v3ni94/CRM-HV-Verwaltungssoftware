import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AiChatWidget, looksLikeContactData, looksLikeImportIntent, pageContext, RUN_TIMEOUT_MS } from "./AiChatWidget";

let pathname = "/kontakte";
vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));
vi.mock("@/lib/ai", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/ai")>()),
  POLL_INTERVAL_MS: 5,
}));

const CONV = "01920000-0000-7000-8000-00000000c001";
const RUN = "01920000-0000-7000-8000-00000000a001";
const PROPOSAL = "01920000-0000-7000-8000-00000000b001";
const DOC = "01920000-0000-7000-8000-00000000d001";

const row = (index: number, status: string) => ({
  index,
  status,
  contact: { first_name: "Test", last_name: `Person ${index}` },
  role: "owner",
  unit_number: null,
  co_members: [],
  confidence: 0.9,
  source_row: index + 2,
  duplicates: [],
  notes: [],
});

describe("pageContext", () => {
  it("derives area and context from the route", () => {
    expect(pageContext("/kontakte")).toEqual({
      area: "contacts",
      contextType: "global",
      contextId: null,
    });
    expect(
      pageContext("/objekte/01920000-0000-7000-8000-00000000e001"),
    ).toEqual({
      area: "properties",
      contextType: "property",
      contextId: "01920000-0000-7000-8000-00000000e001",
    });
    expect(pageContext("/start").area).toBe("other");
  });
});

describe("AiChatWidget", () => {
  afterEach(() => vi.restoreAllMocks());

  it("greets with the page, guides the contact import and applies only after yes", async () => {
    pathname = "/kontakte";
    let runPolls = 0;
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input, init) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/bff/ai/conversations") && method === "POST")
          return jsonResponse(
            {
              id: CONV,
              title: "x",
              context_type: "global",
              context_id: null,
              created_at: "2026-09-24T10:00:00Z",
              messages: [],
            },
            201,
          );
        if (url.endsWith("/api/bff/documents"))
          return jsonResponse({ id: DOC }, 201);
        if (url.endsWith(`/api/bff/ai/conversations/${CONV}/messages`))
          return jsonResponse(
            { id: RUN, status: "queued", task: "extract_contacts" },
            202,
          );
        if (url.endsWith(`/api/bff/ai/runs/${RUN}`)) {
          // First poll still running so the progress bar is observable, then done.
          runPolls += 1;
          if (runPolls < 3)
            return jsonResponse({
              id: RUN,
              status: "running",
              task: "extract_contacts",
              proposal_id: null,
              output: null,
            });
          return jsonResponse({
            id: RUN,
            status: "succeeded",
            task: "extract_contacts",
            proposal_id: PROPOSAL,
            output: {},
          });
        }
        if (url.endsWith(`/api/bff/ai/proposals/${PROPOSAL}`)) {
          return jsonResponse({
            id: PROPOSAL,
            task_run_id: RUN,
            entity_type: "contacts",
            context_id: null,
            decision: "pending",
            decided_by: null,
            decided_at: null,
            import_run_id: null,
            proposed: {
              questions: ["Ist Zeile 4 ein Mieter?"],
              rows: [row(0, "new"), row(1, "new"), row(2, "invalid")],
            },
          });
        }
        if (url.endsWith(`/api/bff/ai/proposals/${PROPOSAL}/apply`)) {
          return jsonResponse({
            id: "imp1",
            source: "ai_contacts",
            status: "applied",
            summary: {},
            created_at: "2026-09-24T10:00:00Z",
            undone_at: null,
            items: [],
          });
        }
        return jsonResponse({}, 404);
      });

    renderIntl(<AiChatWidget />);
    await userEvent.click(
      screen.getByRole("button", { name: "KI-Assistent öffnen" }),
    );
    expect(
      screen.getByText(/Sie sind gerade auf der Seite Kontakte/),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Kontakte importieren" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Eigentümer" }));
    expect(
      screen.getByText(/Bitte hängen Sie die Liste an/),
    ).toBeInTheDocument();

    const file = new File(["a;b"], "eigentuemer.csv", { type: "text/csv" });
    await userEvent.upload(screen.getByLabelText("Datei anhängen"), file);
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));

    await waitFor(() => {
      expect(screen.getByTestId("ai-chat-progress")).toBeInTheDocument();
      expect(screen.getByTestId("ai-chat-pulse")).toBeInTheDocument();
    });

    await waitFor(
      () =>
        expect(
          screen.getByText(/Ich habe 3 Kontakte aus den Daten gelesen/),
        ).toBeInTheDocument(),
      { timeout: 3000 },
    );
    expect(screen.queryByTestId("ai-chat-progress")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-chat-pulse")).not.toBeInTheDocument();
    expect(screen.getByText(/Ist Zeile 4 ein Mieter\?/)).toBeInTheDocument();
    expect(
      screen.getByText(/Soll ich diese 2 Kontakte wirklich importieren\?/),
    ).toBeInTheDocument();
    // The extraction message carries the role chosen by the user.
    const sent = fetchMock.mock.calls.find(([u]) =>
      String(u).endsWith(`/conversations/${CONV}/messages`),
    );
    expect(JSON.parse(sent?.[1]?.body as string)).toMatchObject({
      task: "extract_contacts",
      document_ids: [DOC],
    });
    expect(JSON.parse(sent?.[1]?.body as string).content).toContain(
      "Eigentümer",
    );
    // Nothing applied before the answer.
    expect(
      fetchMock.mock.calls.some(([u]) => String(u).endsWith("/apply")),
    ).toBe(false);

    await userEvent.click(
      screen.getByRole("button", { name: "Ja, importieren" }),
    );
    await waitFor(() =>
      expect(screen.getByText(/Erledigt\./)).toBeInTheDocument(),
    );
    const apply = fetchMock.mock.calls.find(([u]) =>
      String(u).endsWith("/apply"),
    );
    expect(JSON.parse(apply?.[1]?.body as string)).toEqual({
      contacts: [
        { index: 0, action: "create" },
        { index: 1, action: "create" },
        { index: 2, action: "skip" },
      ],
    });
  });

  it("stops polling after the run timeout and names the provider settings", async () => {
    pathname = "/start";
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/bff/ai/conversations") && init?.method === "POST")
        return jsonResponse({ id: CONV, title: "x", context_type: "global", context_id: null, created_at: "2026-09-24T10:00:00Z", messages: [] }, 201);
      if (url.endsWith(`/api/bff/ai/conversations/${CONV}/messages`))
        return jsonResponse({ id: RUN, status: "queued", task: "answer_question" }, 202);
      if (url.endsWith(`/api/bff/ai/runs/${RUN}`)) {
        polled = true;
        return jsonResponse({ id: RUN, status: "running", task: "answer_question", proposal_id: null, output: null });
      }
      return jsonResponse({}, 404);
    });
    // The clock jumps past the limit once the first poll answered; real timers keep the 5 ms poll.
    let polled = false;
    const realNow = Date.now();
    vi.spyOn(Date, "now").mockImplementation(() => realNow + (polled ? RUN_TIMEOUT_MS : 0));

    renderIntl(<AiChatWidget />);
    await userEvent.click(screen.getByRole("button", { name: "KI-Assistent öffnen" }));
    await userEvent.type(screen.getByLabelText("Nachricht"), "Wie hoch ist die Miete?{enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Der Lauf antwortet nicht. Bitte Einstellungen, KI-Anbieter prüfen oder erneut versuchen.",
    );
    expect(screen.queryByTestId("ai-chat-progress")).not.toBeInTheDocument();
  });

  it("imports only the new contacts on request and reports the skipped rows", async () => {
    pathname = "/kontakte";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/bff/ai/conversations") && method === "POST")
        return jsonResponse({ id: CONV, title: "x", context_type: "global", context_id: null, created_at: "2026-09-24T10:00:00Z", messages: [] }, 201);
      if (url.endsWith("/api/bff/documents")) return jsonResponse({ id: DOC }, 201);
      if (url.endsWith(`/api/bff/ai/conversations/${CONV}/messages`))
        return jsonResponse({ id: RUN, status: "queued", task: "extract_contacts" }, 202);
      if (url.endsWith(`/api/bff/ai/runs/${RUN}`))
        return jsonResponse({ id: RUN, status: "succeeded", task: "extract_contacts", proposal_id: PROPOSAL, output: {} });
      if (url.endsWith(`/api/bff/ai/proposals/${PROPOSAL}`))
        return jsonResponse({
          id: PROPOSAL,
          task_run_id: RUN,
          entity_type: "contacts",
          context_id: null,
          decision: "pending",
          decided_by: null,
          decided_at: null,
          import_run_id: null,
          proposed: {
            questions: [],
            rows: [row(0, "new"), row(1, "new"), row(2, "new"), row(3, "incomplete"), row(4, "incomplete"), row(5, "existing"), row(6, "invalid")],
          },
        });
      if (url.endsWith(`/api/bff/ai/proposals/${PROPOSAL}/apply`))
        return jsonResponse({ id: "imp1", source: "ai_contacts", status: "applied", summary: {}, created_at: "2026-09-24T10:00:00Z", undone_at: null, items: [] });
      return jsonResponse({}, 404);
    });

    renderIntl(<AiChatWidget />);
    await userEvent.click(screen.getByRole("button", { name: "KI-Assistent öffnen" }));
    await userEvent.click(screen.getByRole("button", { name: "Kontakte importieren" }));
    await userEvent.click(screen.getByRole("button", { name: "Eigentümer" }));
    await userEvent.upload(screen.getByLabelText("Datei anhängen"), new File(["a;b"], "e.csv", { type: "text/csv" }));
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    await screen.findByText(/Ich habe 7 Kontakte aus den Daten gelesen/, undefined, { timeout: 3000 });

    await userEvent.click(screen.getByRole("button", { name: "Nein" }));
    await userEvent.click(screen.getByRole("button", { name: "Nur neue Kontakte importieren" }));
    await waitFor(() => expect(screen.getByText(/3 Kontakte angelegt\./)).toBeInTheDocument());
    expect(
      screen.getByText(/Übersprungen: 2 unvollständige Zeilen \(ohne Adresse\), 1 bereits vorhandene, 1 ungültige\./),
    ).toBeInTheDocument();
    const apply = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/apply"));
    expect(JSON.parse(apply?.[1]?.body as string).contacts).toEqual([
      { index: 0, action: "create" },
      { index: 1, action: "create" },
      { index: 2, action: "create" },
      { index: 3, action: "skip" },
      { index: 4, action: "skip" },
      { index: 5, action: "skip" },
      { index: 6, action: "skip" },
    ]);
  });

  it("offers a property import on the properties page and asks for a file first", async () => {
    pathname = "/objekte";
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({}, 404),
    );
    renderIntl(<AiChatWidget />);
    await userEvent.click(
      screen.getByRole("button", { name: "KI-Assistent öffnen" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Objekt aus Liste anlegen" }),
    );
    await userEvent.type(screen.getByLabelText("Nachricht"), "hier{enter}");
    expect(
      await screen.findByText(/Dafür brauche ich eine Datei/),
    ).toBeInTheDocument();
  });
});

describe("AiChatWidget free text contacts", () => {
  afterEach(() => vi.restoreAllMocks());

  const conversationAndRun = (fetchMock: ReturnType<typeof vi.fn>, sent: { body?: string }[]) => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/bff/ai/conversations") && method === "POST")
        return jsonResponse({ id: CONV, title: "x", context_type: "global", context_id: null, created_at: "2026-09-24T10:00:00Z", messages: [] }, 201);
      if (url.endsWith(`/api/bff/ai/conversations/${CONV}/messages`)) {
        sent.push({ body: init?.body as string });
        return jsonResponse({ id: RUN, status: "queued", task: "extract_contacts" }, 202);
      }
      if (url.endsWith(`/api/bff/ai/runs/${RUN}`))
        return jsonResponse({ id: RUN, status: "succeeded", task: "extract_contacts", proposal_id: PROPOSAL, output: {} });
      if (url.endsWith(`/api/bff/ai/proposals/${PROPOSAL}`))
        return jsonResponse({
          id: PROPOSAL,
          task_run_id: RUN,
          entity_type: "contacts",
          context_id: null,
          decision: "pending",
          decided_by: null,
          decided_at: null,
          import_run_id: null,
          proposed: { questions: [], rows: [row(0, "new")] },
        });
      return jsonResponse({}, 404);
    });
  };

  it("recognises pasted contact data and offers the import; nothing runs before the yes", () => {
    expect(looksLikeContactData("Erika Muster, Hauptstraße 5, 40213 Düsseldorf, erika@example.org")).toBe(true);
    expect(looksLikeContactData("Wie hoch ist die Miete?")).toBe(false);
    expect(looksLikeImportIntent("Bitte diese Mieter anlegen")).toBe(true);
    expect(looksLikeImportIntent("Wann ist die Versammlung?")).toBe(false);
  });

  it("starts the extraction from the pasted text without a file and keeps the confirmation", async () => {
    pathname = "/start";
    const sent: { body?: string }[] = [];
    const fetchMock = vi.spyOn(globalThis, "fetch");
    conversationAndRun(fetchMock as unknown as ReturnType<typeof vi.fn>, sent);

    renderIntl(<AiChatWidget />);
    await userEvent.click(screen.getByRole("button", { name: "KI-Assistent öffnen" }));
    const pasted = "Erika Muster, Hauptstraße 5, 40213 Düsseldorf, erika@example.org";
    await userEvent.type(screen.getByLabelText("Nachricht"), `${pasted}{enter}`);
    expect(await screen.findByText(/Das sieht nach Kontaktdaten aus/)).toBeInTheDocument();
    expect(sent).toHaveLength(0); // nothing sent before the user says yes
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/api/bff/documents"))).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: "Ja, als Kontakte anlegen" }));
    await userEvent.click(screen.getByRole("button", { name: "Eigentümer" }));
    await waitFor(() => expect(screen.getByText(/Ich habe 1 Kontakte aus den Daten gelesen/)).toBeInTheDocument(), { timeout: 3000 });
    expect(sent).toHaveLength(1);
    const body = JSON.parse(sent[0]?.body as string);
    expect(body).toMatchObject({ task: "extract_contacts", document_ids: [] });
    expect(body.content).toContain("Eigentümer");
    expect(body.content).toContain(pasted);
    // No upload happened and the import still waits for the explicit yes.
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/api/bff/documents"))).toBe(false);
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/apply"))).toBe(false);
    expect(screen.getByRole("button", { name: "Ja, importieren" })).toBeInTheDocument();
  });

  it("offers file or pasted text on an import wish and reads pasted text in the import flow", async () => {
    pathname = "/kontakte";
    const sent: { body?: string }[] = [];
    const fetchMock = vi.spyOn(globalThis, "fetch");
    conversationAndRun(fetchMock as unknown as ReturnType<typeof vi.fn>, sent);

    renderIntl(<AiChatWidget />);
    await userEvent.click(screen.getByRole("button", { name: "KI-Assistent öffnen" }));
    await userEvent.type(screen.getByLabelText("Nachricht"), "Bitte neue Mieter anlegen{enter}");
    expect(await screen.findByText(/Dafür Datei anhängen oder Daten hier einfügen/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Mieter" }));
    expect(screen.getByText(/Bitte hängen Sie die Liste an/)).toBeInTheDocument();
    // Plain text without contact data is not enough.
    await userEvent.type(screen.getByLabelText("Nachricht"), "hier{enter}");
    expect(await screen.findByText(/Bitte eine Datei anhängen .* oder die Kontaktdaten hier als Text einfügen/)).toBeInTheDocument();
    expect(sent).toHaveLength(0);
    await userEvent.type(screen.getByLabelText("Nachricht"), "Max Muster, Tel. 0211 123456, max@example.org{enter}");
    await waitFor(() => expect(screen.getByText(/Ich habe 1 Kontakte aus den Daten gelesen/)).toBeInTheDocument(), { timeout: 3000 });
    const body = JSON.parse(sent[0]?.body as string);
    expect(body).toMatchObject({ task: "extract_contacts", document_ids: [] });
    expect(body.content).toContain("ausschließlich um Mieter");
    expect(body.content).toContain("max@example.org");
  });
});
