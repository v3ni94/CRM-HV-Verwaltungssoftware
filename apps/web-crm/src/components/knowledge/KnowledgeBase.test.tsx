import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { KnowledgeBase, type ExamplePage, type PlaybookRow } from "./KnowledgeBase";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

const playbook: PlaybookRow = {
  id: "p1",
  title: "Telefonnummer ergänzen",
  category: "stammdaten",
  keywords: ["telefon"],
  steps: ["Anrufen", "Erledigung: Stammdaten ergänzt"],
  status: "active",
  usage_count: 3,
  last_used_at: null,
};

const examples: ExamplePage = {
  data: [
    { id: "e1", task: "ticket_resolution", created_at: "2026-09-26T08:00:00Z", decision: "stammdaten_ergaenzt", text: "Telefon nachgetragen" },
  ],
  meta: { page: 1, per_page: 50, total: 1 },
};

describe("KnowledgeBase", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists playbooks and deactivates one", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...playbook, status: "archived" }));
    renderIntl(<KnowledgeBase initialPlaybooks={[playbook]} initialExamples={examples} canManage={true} />);
    expect(screen.getByText("Telefonnummer ergänzen")).toBeInTheDocument();
    expect(screen.getByText("Erledigung: Stammdaten ergänzt")).toBeInTheDocument();
    expect(screen.getByText("nie")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Deaktivieren"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/bff/mail/playbooks/p1");
    expect(JSON.parse(String(init.body))).toEqual({ status: "archived" });
    expect(await screen.findByText("deaktiviert")).toBeInTheDocument();
  });

  it("shows learning examples read only and filters by task", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ data: [], meta: { page: 1, per_page: 50, total: 0 } }));
    renderIntl(<KnowledgeBase initialPlaybooks={[]} initialExamples={examples} canManage={false} />);
    expect(screen.getByText("Noch keine Playbooks gelernt.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Lernbeispiele" }));
    expect(screen.getByText("Telefon nachgetragen")).toBeInTheDocument();
    expect(screen.getByText("Stammdaten ergänzt")).toBeInTheDocument();
    expect(screen.getAllByText("Ticketerledigung").length).toBeGreaterThan(0);
    await userEvent.selectOptions(screen.getByLabelText("Aufgabe filtern"), "ticket_resolution");
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]![0])).toBe("/api/bff/ai/examples?page=1&per_page=50&task=ticket_resolution");
    expect(await screen.findByText("Keine Lernbeispiele.")).toBeInTheDocument();
  });
});
