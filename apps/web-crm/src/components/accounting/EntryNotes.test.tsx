import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, renderIntl } from "@/test/intl";

import { EntryNotes } from "./EntryNotes";

const L = "0192abcd-0000-7000-8000-000000000001";
const E = "0192abcd-0000-7000-8000-000000000002";
const v1 = { id: "n1", note_key: "k", version: 1, supersedes_id: null, body: "Beleg fehlt", created_at: "2026-10-01T08:00:00Z", created_by: null, is_current: false };
const v2 = { ...v1, id: "n2", version: 2, supersedes_id: "n1", body: "Beleg nachgereicht", is_current: true };

describe("EntryNotes", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads notes only on demand and shows all versions", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse([v1, v2]));
    renderIntl(<EntryNotes ledgerId={L} entryId={E} canWrite={false} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    await userEvent.click(screen.getByText("Vermerke"));
    expect(await screen.findByText("Beleg nachgereicht")).toBeInTheDocument();
    expect(screen.getByText("Beleg fehlt")).toBeInTheDocument();
    expect(screen.getAllByTestId("entry-note")).toHaveLength(2);
    expect(screen.queryByText("Vermerk speichern")).not.toBeInTheDocument();
    expect(fetchSpy.mock.calls[0]![0]).toBe(`/api/bff/accounting/ledgers/${L}/entries/${E}/notes`);
  });

  it("creates a new version that references the current one", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([{ ...v1, is_current: true }]))
      .mockResolvedValueOnce(jsonResponse(v2, 201))
      .mockResolvedValueOnce(jsonResponse([v1, v2]));
    renderIntl(<EntryNotes ledgerId={L} entryId={E} canWrite />);
    await userEvent.click(screen.getByText("Vermerke"));
    await userEvent.click(await screen.findByText("Neue Version"));
    const field = screen.getByLabelText("Neue Version des Vermerks");
    await userEvent.clear(field);
    await userEvent.type(field, "Beleg nachgereicht");
    await userEvent.click(screen.getByText("Vermerk speichern"));
    const [url, init] = fetchSpy.mock.calls[1]!;
    expect(url).toBe(`/api/bff/accounting/ledgers/${L}/entries/${E}/notes`);
    expect(JSON.parse(String(init?.body))).toEqual({ body: "Beleg nachgereicht", supersedes_id: "n1" });
    expect(await screen.findByText("Beleg nachgereicht")).toBeInTheDocument();
  });
});
