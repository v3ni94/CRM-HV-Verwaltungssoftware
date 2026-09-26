import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { recordHref, SyncStatus, type SourceDeletion, type SyncState } from "./SyncStatus";

const state: SyncState = {
  enabled: false,
  dump_path: "/data/export.sql",
  last_source_updated_at: "2026-09-20T06:00:00Z",
  last_run_at: "2026-09-25T03:15:00Z",
  last_status: "ok",
  last_error: null,
  last_report: {
    trigger: "scheduled",
    considered: 12,
    created: { documents_document: 2 },
    updated: { objects_unit: 1 },
    deleted_marked: {},
    deletions_resolved: { parties: 1 },
  },
};

const deletion: SourceDeletion = {
  id: "del-1",
  source_table: "objects_managedobject",
  source_id: "12",
  target_table: "property",
  target_id: "11111111-1111-1111-1111-111111111111",
  detected_at: "2026-09-25T03:15:00Z",
  resolved_at: null,
};

describe("SyncStatus", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the last run, its report and open deletion markers with a record link", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse({ items: [deletion] }));
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<SyncStatus initial={state} canEdit canRun />);

    expect(screen.getByText("Erfolgreich")).toBeInTheDocument();
    expect(screen.getByText("25.09.2026 05:15")).toBeInTheDocument();
    const report = screen.getByTestId("sync-report");
    expect(report).toHaveTextContent("Betrachtet12");
    expect(report).toHaveTextContent("Angelegt2documents_document: 2");
    expect(report).toHaveTextContent("Löschmarkierungen aufgelöst1");

    await waitFor(() => expect(screen.getByTestId("sync-deletions")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/bff/objektakte/sync/deletions?");
    expect(screen.getByText("objects_managedobject #12")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Datensatz öffnen" })).toHaveAttribute(
      "href",
      "/objekte/11111111-1111-1111-1111-111111111111",
    );
    expect(screen.getByText("Offen")).toBeInTheDocument();
  });

  it("saves settings, triggers a run without file and reloads the deletion list with resolved ones", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: [] })) // deletions, open only
      .mockResolvedValueOnce(jsonResponse({ ...state, enabled: true })) // PUT
      .mockResolvedValueOnce(jsonResponse({ mode: "queued" })) // POST runs
      .mockResolvedValueOnce(jsonResponse({ items: [{ ...deletion, resolved_at: "2026-09-26T03:15:00Z" }] }));
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<SyncStatus initial={state} canEdit canRun />);
    await waitFor(() => expect(screen.getByText("Keine Löschmarkierungen.")).toBeInTheDocument());

    await act(async () => {
      await userEvent.click(screen.getByLabelText("Täglicher Abgleich aktiv"));
      await userEvent.click(screen.getByRole("button", { name: "Einstellungen speichern" }));
    });
    expect(screen.getByText("Einstellungen gespeichert.")).toBeInTheDocument();
    const put = fetchMock.mock.calls[1];
    expect(String(put?.[0])).toBe("/api/bff/objektakte/sync");
    expect(put?.[1]?.method).toBe("PUT");
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({ enabled: true, dump_path: "/data/export.sql" });

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Jetzt abgleichen" }));
    });
    const run = fetchMock.mock.calls[2];
    expect(String(run?.[0])).toBe("/api/bff/objektakte/sync/runs");
    expect(run?.[1]?.method).toBe("POST");
    expect(run?.[1]?.body).toBeUndefined();
    expect(screen.getByText(/an den Worker übergeben/)).toBeInTheDocument();

    await act(async () => {
      await userEvent.selectOptions(screen.getByLabelText("Löschmarkierungen"), "all");
    });
    await waitFor(() => expect(screen.getByText("26.09.2026 05:15")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[3]?.[0])).toBe("/api/bff/objektakte/sync/deletions?include_resolved=true");
  });

  it("hides the settings and run actions without permissions", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ items: [] })));
    renderIntl(<SyncStatus initial={state} canEdit={false} canRun={false} />);
    expect(screen.queryByRole("button", { name: "Einstellungen speichern" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Jetzt abgleichen" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Täglicher Abgleich aktiv")).toBeDisabled();
    await waitFor(() => expect(screen.getByText("Keine Löschmarkierungen.")).toBeInTheDocument());
  });

  it("links only records with an own page", () => {
    expect(recordHref("contact", "c1")).toBe("/kontakte/c1");
    expect(recordHref("objektakte_drive_node", "n1")).toBeNull();
    expect(recordHref("property", null)).toBeNull();
  });
});
