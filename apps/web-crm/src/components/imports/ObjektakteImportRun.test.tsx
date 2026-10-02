import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MigrationHistory } from "./MigrationHistory";
import { ObjektakteImportRun } from "./ObjektakteImportRun";
import { PreviewImportRun } from "./PreviewImportRun";

const RUN = "0190a1b2-0000-7000-8000-000000000001";

afterEach(() => vi.restoreAllMocks());

describe("ObjektakteImportRun", () => {
  it("applies only after a preview and shows the OCR result", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url.includes("ocr-cache")) return jsonResponse({ import_run_id: RUN, matched: 3, unmatched_keys: ["k1"], unmatched_count: 1 });
      if (url.includes("mode=apply")) return jsonResponse({ mode: "apply", import_run_id: RUN });
      return jsonResponse({ mode: "preview", new_properties: 2 });
    });
    const { container } = renderIntl(<ObjektakteImportRun />);
    const [dump, zip] = Array.from(container.querySelectorAll<HTMLInputElement>('input[type="file"]'));
    expect(screen.getByRole("button", { name: "Übernehmen" })).toBeDisabled();
    await userEvent.upload(dump!, new File(["x"], "dump.sql"));
    await userEvent.click(screen.getByRole("button", { name: "Prüfen (Vorschau)" }));
    await screen.findByTestId("import-preview");
    await userEvent.click(screen.getByRole("button", { name: "Übernehmen" }));
    await waitFor(() => expect(calls.some((c) => c.includes("mode=apply"))).toBe(true));
    await userEvent.upload(zip!, new File(["z"], "ocr.zip"));
    await waitFor(() => expect(screen.getByRole("button", { name: "OCR-Cache übernehmen" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "OCR-Cache übernehmen" }));
    expect(await screen.findByTestId("ocr-result")).toHaveTextContent("3 Dokumente zugeordnet, 1 Schlüssel");
  });
});

describe("PreviewImportRun", () => {
  it("shows the last run and offers resume after a failure", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ previews_dir: "/x", run: { id: RUN, status: "failed", total: 10, processed: 4, imported: 3, rendered: 0, missing: 1, skipped: 0, failed: 1, started_at: "2026-10-01T10:00:00Z", finished_at: null, error: "boom" } }),
    );
    renderIntl(<PreviewImportRun canStart />);
    expect(await screen.findByTestId("preview-run")).toHaveTextContent("4 von 10");
    expect(screen.getByRole("button", { name: "Nach Abbruch fortsetzen" })).toBeInTheDocument();
  });
  it("hides start for readers", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ previews_dir: "/x", run: null }));
    renderIntl(<PreviewImportRun canStart={false} />);
    await screen.findByText("Noch kein Lauf.");
    expect(screen.queryByRole("button", { name: "Lauf starten" })).toBeNull();
  });
});

describe("MigrationHistory", () => {
  it("loads open items with the open sum", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse([
        { id: "a", kind: "receivable", source_item_id: "1", original_due_date: "2025-01-01", original_amount: "100.10", paid_amount: "0.00", open_amount: "100.10", description: null },
        { id: "b", kind: "deposit", source_item_id: "2", original_due_date: null, original_amount: "50.20", paid_amount: "0.00", open_amount: "50.20", description: null },
      ]),
    );
    renderIntl(<MigrationHistory ledgers={[{ id: "L1", name: "WEG" }]} canTickets={false} />);
    await userEvent.selectOptions(screen.getByLabelText("Buchungskreis"), "L1");
    await userEvent.click(screen.getByRole("button", { name: "Einzelposten laden" }));
    expect(await screen.findByTestId("history-items")).toHaveTextContent("2 Einzelposten");
    expect(screen.getByTestId("history-items")).toHaveTextContent("150,30");
  });
});
