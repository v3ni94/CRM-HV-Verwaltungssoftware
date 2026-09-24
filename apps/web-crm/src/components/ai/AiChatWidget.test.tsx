import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AiChatWidget, pageContext } from "./AiChatWidget";

let pathname = "/kontakte";
vi.mock("next/navigation", () => ({ usePathname: () => pathname, useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/lib/ai", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/ai")>()), POLL_INTERVAL_MS: 5 }));

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
    expect(pageContext("/kontakte")).toEqual({ area: "contacts", contextType: "global", contextId: null });
    expect(pageContext("/objekte/01920000-0000-7000-8000-00000000e001")).toEqual({
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
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/bff/ai/conversations") && method === "POST") return jsonResponse({ id: CONV, title: "x", context_type: "global", context_id: null, created_at: "2026-09-24T10:00:00Z", messages: [] }, 201);
      if (url.endsWith("/api/bff/documents")) return jsonResponse({ id: DOC }, 201);
      if (url.endsWith(`/api/bff/ai/conversations/${CONV}/messages`)) return jsonResponse({ id: RUN, status: "queued", task: "extract_contacts" }, 202);
      if (url.endsWith(`/api/bff/ai/runs/${RUN}`)) return jsonResponse({ id: RUN, status: "succeeded", task: "extract_contacts", proposal_id: PROPOSAL, output: {} });
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
          proposed: { questions: ["Ist Zeile 4 ein Mieter?"], rows: [row(0, "new"), row(1, "new"), row(2, "invalid")] },
        });
      }
      if (url.endsWith(`/api/bff/ai/proposals/${PROPOSAL}/apply`)) {
        return jsonResponse({ id: "imp1", source: "ai_contacts", status: "applied", summary: {}, created_at: "2026-09-24T10:00:00Z", undone_at: null, items: [] });
      }
      return jsonResponse({}, 404);
    });

    renderIntl(<AiChatWidget />);
    await userEvent.click(screen.getByRole("button", { name: "KI-Assistent öffnen" }));
    expect(screen.getByText(/Sie sind gerade auf der Seite Kontakte/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Kontakte importieren" }));
    await userEvent.click(screen.getByRole("button", { name: "Eigentümer" }));
    expect(screen.getByText(/Bitte hängen Sie die Liste an/)).toBeInTheDocument();

    const file = new File(["a;b"], "eigentuemer.csv", { type: "text/csv" });
    await userEvent.upload(screen.getByLabelText("Datei anhängen"), file);
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));

    await waitFor(() => expect(screen.getByText(/Ich habe 3 Kontakte aus den Daten gelesen/)).toBeInTheDocument(), { timeout: 3000 });
    expect(screen.getByText(/Ist Zeile 4 ein Mieter\?/)).toBeInTheDocument();
    expect(screen.getByText(/Soll ich diese 2 Kontakte wirklich importieren\?/)).toBeInTheDocument();
    // The extraction message carries the role chosen by the user.
    const sent = fetchMock.mock.calls.find(([u]) => String(u).endsWith(`/conversations/${CONV}/messages`));
    expect(JSON.parse(sent?.[1]?.body as string)).toMatchObject({ task: "extract_contacts", document_ids: [DOC] });
    expect(JSON.parse(sent?.[1]?.body as string).content).toContain("Eigentümer");
    // Nothing applied before the answer.
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/apply"))).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: "Ja, importieren" }));
    await waitFor(() => expect(screen.getByText(/Erledigt\./)).toBeInTheDocument());
    const apply = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/apply"));
    expect(JSON.parse(apply?.[1]?.body as string)).toEqual({
      contacts: [
        { index: 0, action: "create" },
        { index: 1, action: "create" },
        { index: 2, action: "skip" },
      ],
    });
  });

  it("offers a property import on the properties page and asks for a file first", async () => {
    pathname = "/objekte";
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}, 404));
    renderIntl(<AiChatWidget />);
    await userEvent.click(screen.getByRole("button", { name: "KI-Assistent öffnen" }));
    await userEvent.click(screen.getByRole("button", { name: "Objekt aus Liste anlegen" }));
    await userEvent.type(screen.getByLabelText("Nachricht"), "hier{enter}");
    expect(await screen.findByText(/Dafür brauche ich eine Datei/)).toBeInTheDocument();
  });
});
