import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { ImportField, ImportMapping, ImportSource } from "@/lib/immoware";
import { jsonResponse, renderIntl } from "@/test/intl";

import { MappingStep } from "./MappingStep";

const SOURCE_ID = "01920000-0000-7000-8000-0000000000aa";
const source: ImportSource = {
  id: SOURCE_ID,
  document_id: "01920000-0000-7000-8000-0000000000bb",
  report_type: "units",
  sheet: null,
  header_row: 1,
  headers: ["Objektnr", "Einheit", "Art"],
  row_count: 3,
  mapping_id: null,
  status: "uploaded",
  import_run_id: null,
  report: {},
};
const fields: ImportField[] = [
  { name: "property_number", label: "Objektnummer", kind: "text", required: true, choices: [] },
  { name: "number", label: "Einheitsnummer", kind: "text", required: true, choices: [] },
  { name: "kind", label: "Art", kind: "choice", required: false, choices: ["apartment", "commercial"] },
];
const rows = [
  { row_number: 2, raw: { Objektnr: "1", Einheit: "01", Art: "Wohnung" }, values: null, status: "pending", errors: [], entity_type: null, entity_id: null },
  { row_number: 3, raw: { Objektnr: "1", Einheit: "02", Art: "Gewerbe" }, values: null, status: "pending", errors: [], entity_type: null, entity_id: null },
  { row_number: 4, raw: { Objektnr: "1", Einheit: "03", Art: "Wohnung" }, values: null, status: "pending", errors: [], entity_type: null, entity_id: null },
];

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("MappingStep", () => {
  it("marks required fields and blocks saving until they are assigned", async () => {
    fetchMock.mockResolvedValue(jsonResponse(rows));
    const onMapping = vi.fn();
    renderIntl(<MappingStep source={source} fields={fields} mappings={[]} onMapping={onMapping} />);
    expect(screen.getAllByText("(Pflichtfeld)")).toHaveLength(2);
    expect(screen.getByTestId("required-missing")).toHaveTextContent("Objektnummer, Einheitsnummer");
    const save = screen.getByRole("button", { name: /neue Vorlagenversion/ });
    expect(save).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText(/Objektnummer/), "Objektnr");
    await userEvent.selectOptions(screen.getByLabelText(/Einheitsnummer/), "Einheit");
    expect(screen.queryByTestId("required-missing")).not.toBeInTheDocument();
    expect(save).toBeEnabled();
  });

  it("lists distinct source values of choice fields and saves value maps", async () => {
    const saved: ImportMapping = { id: "m1", report_type: "units", name: "Standard", version: 2, columns: {}, value_maps: {}, active: true };
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "POST" ? jsonResponse(saved, 201) : jsonResponse(rows)),
    );
    const onMapping = vi.fn();
    renderIntl(<MappingStep source={source} fields={fields} mappings={[]} onMapping={onMapping} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(`/api/bff/imports/immoware24/files/${SOURCE_ID}/rows?limit=200`, expect.anything()));
    await userEvent.selectOptions(screen.getByLabelText(/Objektnummer/), "Objektnr");
    await userEvent.selectOptions(screen.getByLabelText(/Einheitsnummer/), "Einheit");
    await userEvent.selectOptions(screen.getByLabelText(/^Art/), "Art");
    const box = await screen.findByTestId("value-map-kind");
    expect(box).toHaveTextContent("Wohnung");
    expect(box).toHaveTextContent("Gewerbe");
    await userEvent.selectOptions(screen.getByLabelText("Wohnung"), "apartment");
    await userEvent.type(screen.getByLabelText("Name der Vorlage"), "Standard");
    await userEvent.click(screen.getByRole("button", { name: /neue Vorlagenversion/ }));
    await waitFor(() => expect(onMapping).toHaveBeenCalledWith(saved));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(post[0]).toBe("/api/bff/imports/immoware24/mappings");
    expect(JSON.parse(post[1].body as string)).toEqual({
      report_type: "units",
      name: "Standard",
      columns: { property_number: "Objektnr", number: "Einheit", kind: "Art" },
      value_maps: { kind: { Wohnung: "apartment" } },
    });
  });

  it("offers existing template versions of the same report type", async () => {
    fetchMock.mockResolvedValue(jsonResponse(rows));
    const tpl: ImportMapping = {
      id: "m7",
      report_type: "units",
      name: "Immoware Standard",
      version: 3,
      columns: { property_number: "Objektnr", number: "Einheit" },
      value_maps: {},
      active: true,
    };
    const other: ImportMapping = { ...tpl, id: "m8", report_type: "contacts", name: "Kontakte" };
    const onMapping = vi.fn();
    renderIntl(<MappingStep source={source} fields={fields} mappings={[tpl, other]} onMapping={onMapping} />);
    expect(screen.queryByText("Kontakte, Version 3")).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Vorhandene Vorlage"), "m7");
    expect(screen.getByLabelText(/Objektnummer/)).toHaveValue("Objektnr");
    await userEvent.click(screen.getByRole("button", { name: "Vorlage verwenden und prüfen" }));
    expect(onMapping).toHaveBeenCalledWith(tpl);
  });
});
