import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { KnowledgeEntry } from "@/lib/ai";
import { jsonResponse, renderIntl } from "@/test/intl";

import { KnowledgeSettings } from "./KnowledgeSettings";

const entry: KnowledgeEntry = {
  id: "01920000-0000-7000-8000-0000000000k1",
  property_id: null,
  kind: "workflow",
  title: "Ablage",
  content: "Rechnungen nach Objekt.",
  source: "manual",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  created_by: null,
};

describe("KnowledgeSettings", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists existing entries and creates a new one", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([entry])) // reload on property filter effect (none set initially skipped, first call is create)
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
});
