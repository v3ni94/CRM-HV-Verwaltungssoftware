import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { type ExportRun, ObjektakteExportPanel } from "./ObjektakteExportPanel";

const PROPERTY = "01920000-0000-7000-8000-0000000000p1";
const RUN: ExportRun = {
  id: "01920000-0000-7000-8000-0000000000e1",
  status: "done",
  document_id: "01920000-0000-7000-8000-0000000000d1",
  counts: { documents: 3, units: 2, owners: 2, tenants: 0, open_items: 1 },
  error: null,
  created_at: "2026-09-29T10:00:00Z",
  finished_at: "2026-09-29T10:01:00Z",
  download_count: 1,
};
const NOTE = "Datenschutzhinweis: nur für den Nachfolger.";

describe("ObjektakteExportPanel", () => {
  const calls: { url: string; method: string; body: unknown }[] = [];
  let items: ExportRun[] = [];
  beforeEach(() => {
    calls.length = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (method === "POST") {
        items = [{ ...RUN, status: "queued", document_id: null, counts: {}, download_count: 0 }];
        return jsonResponse(items[0], 202);
      }
      return jsonResponse({ items, personal_data_note: NOTE, can_start: true });
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("starts the export only after the confirmation with the personal data note", async () => {
    items = [];
    renderIntl(<ObjektakteExportPanel propertyId={PROPERTY} canExport />);
    expect(await screen.findByText("Noch kein Export.")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("export-start"));
    expect(screen.getByTestId("export-note")).toHaveTextContent(NOTE);
    expect(screen.getByTestId("export-confirm")).toBeDisabled();
    await userEvent.click(screen.getByTestId("export-acknowledge"));
    await userEvent.click(screen.getByTestId("export-confirm"));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")).toMatchObject({
      url: `/api/bff/properties/${PROPERTY}/objektakte-export`,
      body: { confirm: true, personal_data_acknowledged: true, note: null },
    });
    expect(await screen.findByText("Export gestartet, das ZIP erscheint hier nach Abschluss.")).toBeInTheDocument();
    expect(await screen.findByText("wartet")).toBeInTheDocument();
  });

  it("lists a finished export with counts and the download link", async () => {
    items = [RUN];
    renderIntl(<ObjektakteExportPanel propertyId={PROPERTY} canExport />);
    expect(await screen.findByText("fertig")).toBeInTheDocument();
    expect(screen.getByText("3 Dokumente, 2 Einheiten, 2 Eigentümer, 0 Mieter, 1 offene Posten")).toBeInTheDocument();
    expect(screen.getByTestId(`export-download-${RUN.id}`)).toHaveAttribute("href", `/api/bff/properties/${PROPERTY}/objektakte-export/${RUN.id}/download`);
    expect(screen.getByText("1 Abruf")).toBeInTheDocument();
  });

  it("stays read only without the permissions", async () => {
    items = [RUN];
    renderIntl(<ObjektakteExportPanel propertyId={PROPERTY} canExport={false} />);
    expect(await screen.findByText("Zum Export sind die Rechte properties:update und documents:read erforderlich.")).toBeInTheDocument();
    expect(screen.queryByTestId("export-start")).not.toBeInTheDocument();
    expect(screen.queryByTestId(`export-download-${RUN.id}`)).not.toBeInTheDocument();
  });
});
