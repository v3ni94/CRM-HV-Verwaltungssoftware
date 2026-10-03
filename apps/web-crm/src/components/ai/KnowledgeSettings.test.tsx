import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { KnowledgeEntry } from "@/lib/ai";
import { jsonResponse, renderIntl } from "@/test/intl";

import { KnowledgeSettings } from "./KnowledgeSettings";

const entry = {
  id: "01920000-0000-7000-8000-0000000000k1",
  property_id: null,
  kind: "workflow",
  title: "Ablage",
  content: "Rechnungen nach Objekt.",
  source: "manual",
  status: "draft",
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  created_by: null,
} as unknown as KnowledgeEntry;

describe("KnowledgeSettings", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists existing entries and creates a new one", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ ...entry, id: "01920000-0000-7000-8000-0000000000k2", title: "Neu" }))
      .mockResolvedValueOnce(jsonResponse([entry, { ...entry, id: "01920000-0000-7000-8000-0000000000k2", title: "Neu" }]));
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<KnowledgeSettings initial={[entry]} properties={[{ id: "p1", number: "042", name: "Musterhaus" }]} />);

    expect(screen.getByText("Ablage")).toBeInTheDocument();

    await act(async () => {
      await userEvent.type(screen.getByLabelText("Titel"), "Neu");
      await userEvent.type(screen.getByLabelText("Inhalt"), "Ein neuer Inhalt.");
      await userEvent.click(screen.getByRole("button", { name: "Anlegen" }));
    });

    expect(screen.getByText("Neu")).toBeInTheDocument();
  });

  it("shows usage, helpfulness and the stale hint of an approved entry (audit 29.09.2026)", () => {
    const stale = {
      ...entry,
      id: "01920000-0000-7000-8000-0000000000k3",
      title: "Alte Regel",
      status: "approved",
      usage_count: 7,
      helpful_count: 3,
      unhelpful_count: 1,
      stale: true,
    } as unknown as KnowledgeEntry;
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse([entry, stale])));
    renderIntl(<KnowledgeSettings initial={[entry, stale]} properties={[]} />);
    const usages = screen.getAllByTestId("knowledge-usage");
    expect(usages[0]).toHaveTextContent("0x verwendet · 0 hilfreich, 0 nicht hilfreich");
    expect(usages[1]).toHaveTextContent("7x verwendet · 3 hilfreich, 1 nicht hilfreich");
    expect(screen.getAllByText("Lange nicht geprüft")).toHaveLength(1);
  });

  it("does not refetch the list on mount, only when a filter changes", async () => {
    const fetchMock = vi.fn(async () => jsonResponse([entry]));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<KnowledgeSettings initial={[entry]} properties={[]} />);
    await act(async () => {});
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows feedback buttons on approved entries only with ai:create (GAI-301)", () => {
    const approved = { ...entry, status: "approved" } as unknown as KnowledgeEntry;
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse([approved])));
    const { unmount } = renderIntl(<KnowledgeSettings initial={[approved]} properties={[]} canFeedback />);
    expect(screen.getAllByRole("button", { name: "Hilfreich" }).length).toBeGreaterThan(0);
    unmount();
    renderIntl(<KnowledgeSettings initial={[approved]} properties={[]} canFeedback={false} />);
    expect(screen.queryByRole("button", { name: "Hilfreich" })).not.toBeInTheDocument();
  });
});
