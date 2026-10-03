import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { ImportSource } from "@/lib/immoware";
import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { Immoware24Wizard } from "./Immoware24Wizard";

vi.mock("./MappingStep", () => ({ MappingStep: () => <div data-testid="mapping-step" /> }));
vi.mock("@/components/ai/ImportUndoButton", () => ({ ImportUndoButton: () => <button type="button">undo</button> }));

const m = messages.Immoware24;
const source: ImportSource = {
  id: "01920000-0000-7000-8000-0000000000aa",
  document_id: "01920000-0000-7000-8000-0000000000bb",
  report_type: "properties",
  sheet: null,
  header_row: 3,
  headers: ["Objektnr", "Name"],
  row_count: 5,
  mapping_id: null,
  status: "uploaded",
  import_run_id: null,
  report: {},
};

async function toUpload() {
  renderIntl(<Immoware24Wizard fields={{}} mappings={[]} canUndo={false} />);
  await userEvent.click(screen.getByRole("button", { name: m.next }));
}

describe("Immoware24Wizard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("requires a file before anything is sent", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    await toUpload();
    await userEvent.click(screen.getByRole("button", { name: m.uploadSubmit }));
    expect(await screen.findByRole("alert")).toHaveTextContent(m.fileRequired);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the API refusal of the document upload and stays on the upload step", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Fehler", status: 413, detail: "Datei zu groß" }, 413));
    await toUpload();
    await userEvent.click(screen.getByLabelText(m.detect.autoHeader));
    await userEvent.upload(document.querySelector('input[type="file"]') as HTMLInputElement, new File(["a"], "objekte.csv", { type: "text/csv" }));
    await userEvent.click(screen.getByRole("button", { name: m.uploadSubmit }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Datei zu groß");
    expect(screen.queryByTestId("mapping-step")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: m.uploadSubmit })).toBeEnabled();
  });

  it("uploads, registers the source with the chosen header row and moves to the mapping step", async () => {
    const calls: { url: string; body: unknown }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, body: init?.body });
      if (url.endsWith("/api/bff/documents")) return jsonResponse({ id: source.document_id });
      return jsonResponse(source);
    });
    await toUpload();
    await userEvent.click(screen.getByLabelText(m.detect.autoHeader));
    const row = screen.getByLabelText(m.headerRow);
    await userEvent.clear(row);
    await userEvent.type(row, "3");
    await userEvent.upload(document.querySelector('input[type="file"]') as HTMLInputElement, new File(["a"], "objekte.csv", { type: "text/csv" }));
    await userEvent.click(screen.getByRole("button", { name: m.uploadSubmit }));
    await waitFor(() => expect(screen.getByTestId("mapping-step")).toBeInTheDocument());
    expect(calls[0]!.url).toBe("/api/bff/documents");
    expect(calls[0]!.body).toBeInstanceOf(FormData);
    expect(calls[1]!.url).toBe("/api/bff/imports/immoware24/files");
    expect(JSON.parse(String(calls[1]!.body))).toMatchObject({ report_type: "properties", header_row: 3, document_id: source.document_id });
  });
});
