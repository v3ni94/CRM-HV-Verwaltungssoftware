import type { components } from "@mhvp/api-client";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

import { NotesPanel } from "./NotesPanel";

type Note = components["schemas"]["NoteOut"];
const note: Note = {
  id: "n1",
  body: "Alter Text",
  category: null,
  title: null,
  pinned: false,
  follow_up_on: null,
  created_at: "2026-09-01T08:00:00Z",
  created_by: null,
};

describe("NotesPanel maintenance", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockClear();
  });

  it("changes the text with PATCH", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ ...note, body: "Neuer Text" }));
    renderIntl(<NotesPanel contactId="c1" notes={[note]} />);
    await userEvent.click(screen.getByRole("button", { name: "Ändern" }));
    const area = screen.getByDisplayValue("Alter Text");
    await userEvent.clear(area);
    await userEvent.type(area, "Neuer Text");
    await userEvent.click(screen.getByRole("button", { name: "Änderung speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/bff/contacts/c1/notes/n1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({ body: "Neuer Text" });
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("pins and deletes after confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(note));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<NotesPanel contactId="c1" notes={[note]} />);
    await userEvent.click(screen.getByRole("button", { name: "Anheften" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(JSON.parse(String((fetchMock.mock.calls[0]![1] as RequestInit).body))).toEqual({ pinned: true });
    await userEvent.click(screen.getByRole("button", { name: "Löschen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect((fetchMock.mock.calls[1]![1] as RequestInit).method).toBe("DELETE");
  });

  it("does not delete without confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(note));
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderIntl(<NotesPanel contactId="c1" notes={[note]} />);
    await userEvent.click(screen.getByRole("button", { name: "Löschen" }));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
