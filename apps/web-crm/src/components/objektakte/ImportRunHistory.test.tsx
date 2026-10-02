import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ImportRunHistory, type ImportRunRow } from "./ImportRunHistory";

const row: ImportRunRow = {
  id: "11111111-1111-1111-1111-111111111111",
  status: "applied",
  created_at: "2026-09-25T03:15:00Z",
  created_total: 12,
  updated_total: 3,
  skipped_duplicates_total: 4,
  considered_total: 19,
  deleted_marked: 0,
  cache_documents: 5,
};

const previewState = {
  previews_dir: "/data/previews",
  run: {
    status: "done",
    trigger: "manual",
    total: 10,
    processed: 10,
    imported: 8,
    rendered: 0,
    missing: 2,
    skipped: 0,
    failed: 0,
    started_at: "2026-09-26T08:00:00Z",
    finished_at: "2026-09-26T08:05:00Z",
    error: null,
  },
};

function route(handlers: Record<string, () => Response>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${String(input).split("?")[0]}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`unexpected ${key}`);
    return handler();
  });
}

describe("ImportRunHistory", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists the runs with counts and shows the latest preview run", async () => {
    vi.stubGlobal(
      "fetch",
      route({
        "GET /api/bff/objektakte/import-runs": () => jsonResponse([row], 200, { "x-total-count": "1" }),
        "GET /api/bff/objektakte/previews/import": () => jsonResponse(previewState),
      }),
    );
    renderIntl(<ImportRunHistory canClear canStartPreviews />);

    const table = await screen.findByTestId("import-runs");
    expect(table).toHaveTextContent("25.09.2026 05:15");
    expect(table).toHaveTextContent("applied");
    expect(await screen.findByTestId("preview-run")).toHaveTextContent("Abgeschlossen");
    expect(screen.getByTestId("preview-run")).toHaveTextContent("10 / 10");
  });

  it("asks for confirmation before clearing the OCR cache and then reloads", async () => {
    const fetchMock = route({
      "GET /api/bff/objektakte/import-runs": () => jsonResponse([row], 200, { "x-total-count": "1" }),
      "GET /api/bff/objektakte/previews/import": () => jsonResponse({ previews_dir: null, run: null }),
      [`DELETE /api/bff/objektakte/import-runs/${row.id}/ocr-cache`]: () => jsonResponse({ import_run_id: row.id, cleared: 5 }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderIntl(<ImportRunHistory canClear canStartPreviews={false} />);

    await user.click(await screen.findByTestId(`clear-cache-${row.id}`));
    // Cancel: nothing is deleted.
    await user.click(await screen.findByRole("button", { name: "Abbrechen" }));
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);

    await user.click(await screen.findByTestId(`clear-cache-${row.id}`));
    await act(async () => {
      await user.click(await screen.findByTestId("confirm-sheet-confirm"));
    });
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(true));
    expect(await screen.findByText("5 Texte entfernt.")).toBeInTheDocument();
    expect(screen.queryByTestId("start-previews")).not.toBeInTheDocument();
  });

  it("shows the API error and starts the preview takeover", async () => {
    const fetchMock = route({
      "GET /api/bff/objektakte/import-runs": () =>
        jsonResponse({ title: "Forbidden", detail: "Keine Berechtigung" }, 403),
      "GET /api/bff/objektakte/previews/import": () => jsonResponse({ previews_dir: null, run: null }),
      "POST /api/bff/objektakte/previews/import": () => jsonResponse({ mode: "queued" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderIntl(<ImportRunHistory canClear={false} canStartPreviews />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await user.click(await screen.findByTestId("start-previews"));
    expect(await screen.findByText("Die Übernahme der Vorschaubilder wurde gestartet.")).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ render_missing: false, resume: true });
  });

  it("shows an empty state without runs", async () => {
    vi.stubGlobal(
      "fetch",
      route({
        "GET /api/bff/objektakte/import-runs": () => jsonResponse([], 200, { "x-total-count": "0" }),
        "GET /api/bff/objektakte/previews/import": () => jsonResponse({ previews_dir: null, run: null }),
      }),
    );
    renderIntl(<ImportRunHistory canClear canStartPreviews />);
    expect(await screen.findByText("Noch keine Importläufe.")).toBeInTheDocument();
  });
});
