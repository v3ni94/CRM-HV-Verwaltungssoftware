import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { ColumnCheck, ColumnProposal, ExportRequirement, ImportField, ImportMapping, ImportSource } from "@/lib/immoware";
import { assignmentsFrom, proposedColumns } from "@/lib/immoware";
import { jsonResponse, renderIntl } from "@/test/intl";

import { ColumnCheckReport } from "./ColumnCheckReport";
import { ExportRequirements } from "./ExportRequirements";
import { MappingStep } from "./MappingStep";

const SOURCE_ID = "01920000-0000-7000-8000-0000000000aa";
const source: ImportSource = {
  id: SOURCE_ID,
  document_id: "01920000-0000-7000-8000-0000000000bb",
  report_type: "units",
  sheet: null,
  header_row: 3,
  headers: ["Objekt-Nr.", "Einheit", "Bemerkung"],
  row_count: 2,
  mapping_id: null,
  status: "uploaded",
  import_run_id: null,
  report: {},
};
const fields: ImportField[] = [
  { name: "property_number", label: "Objektnummer", kind: "text", required: true, choices: [] },
  { name: "number", label: "Einheitennummer", kind: "text", required: true, choices: [] },
];
const proposal: ColumnProposal = {
  report_type: "units",
  headers: source.headers,
  columns: { property_number: "Objekt-Nr.", number: "Einheit" },
  fields: [
    { name: "property_number", label: "Objektnummer", required: true, header: "Objekt-Nr.", score: 95, basis: "label", basis_label: "Feldbezeichnung", status: "sure", note: null, alternatives: [] },
    { name: "number", label: "Einheitennummer", required: true, header: "Einheit", score: 100, basis: "stored", basis_label: "gespeicherte Zuordnung", status: "stored", note: null, alternatives: [] },
  ],
  unassigned_headers: ["Bemerkung"],
  ignored_headers: [],
  missing_required: [],
  stored_used: 1,
};
const check: ColumnCheck = {
  report_type: "units",
  rows: 2,
  valid: 1,
  invalid: 1,
  staged_only: false,
  required: [
    { name: "property_number", label: "Objektnummer", header: "Objekt-Nr.", status: "ok", empty: 0 },
    { name: "number", label: "Einheitennummer", header: "Einheit", status: "partly_empty", empty: 1 },
  ],
  fields: [
    { name: "property_number", label: "Objektnummer", header: "Objekt-Nr.", filled: 2, empty: 0, errors: 0, examples: ["001"] },
    { name: "number", label: "Einheitennummer", header: "Einheit", filled: 1, empty: 1, errors: 1, examples: ["01"] },
  ],
  not_in_file: [],
  assigned_twice: [],
  unassigned_headers: ["Bemerkung"],
  sample_rows: [{ row_number: 4, raw: { "Objekt-Nr.": "001", Einheit: "01" }, values: { property_number: "001", number: "01" }, errors: [] }],
  error_rows: [{ row_number: 5, raw: { "Objekt-Nr.": "001", Einheit: null }, values: { property_number: "001" }, errors: ["Einheitennummer: fehlt"] }],
  ready: true,
};

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function route(saved?: ImportMapping) {
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/column-proposal")) return Promise.resolve(jsonResponse(proposal));
    if (url.endsWith("/check")) return Promise.resolve(jsonResponse(check));
    if (url.endsWith("/column-assignments")) return Promise.resolve(jsonResponse([]));
    if (init?.method === "POST" && saved) return Promise.resolve(jsonResponse(saved, 201));
    return Promise.resolve(jsonResponse([]));
  });
}

describe("column detection (AE37)", () => {
  it("prefills the mapping from the proposal and shows basis and score", async () => {
    route();
    renderIntl(<MappingStep source={source} fields={fields} mappings={[]} onMapping={vi.fn()} />);
    await waitFor(() => expect(screen.getByLabelText(/Objektnummer/)).toHaveValue("Objekt-Nr."));
    expect(screen.getByLabelText(/Einheitennummer/)).toHaveValue("Einheit");
    expect(screen.getByTestId("proposal-notice")).toHaveTextContent("2 Zielfelder zugeordnet, davon 1 aus gespeicherten Zuordnungen");
    expect(screen.getByTestId("proposal-property_number")).toHaveTextContent("sicher 95 %");
    expect(screen.getByTestId("proposal-number")).toHaveTextContent("gespeichert 100 %");
    expect(screen.queryByTestId("required-missing")).not.toBeInTheDocument();
  });

  it("remembers the confirmed assignment when the template is saved", async () => {
    const saved: ImportMapping = { id: "m1", report_type: "units", name: "Standard", version: 1, columns: {}, value_maps: {}, active: true };
    route(saved);
    const onMapping = vi.fn();
    renderIntl(<MappingStep source={source} fields={fields} mappings={[]} onMapping={onMapping} />);
    await waitFor(() => expect(screen.getByLabelText(/Objektnummer/)).toHaveValue("Objekt-Nr."));
    await userEvent.type(screen.getByLabelText("Name der Vorlage"), "Standard");
    await userEvent.click(screen.getByRole("button", { name: /neue Vorlagenversion/ }));
    await waitFor(() => expect(onMapping).toHaveBeenCalledWith(saved));
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(put[0]).toBe("/api/bff/imports/immoware24/column-assignments");
    expect(JSON.parse(put[1].body as string)).toEqual({
      report_type: "units",
      assignments: [
        { header: "Objekt-Nr.", target_field: "property_number" },
        { header: "Einheit", target_field: "number" },
      ],
    });
  });

  it("does not remember when the box is cleared", async () => {
    const saved: ImportMapping = { id: "m2", report_type: "units", name: "Ohne", version: 1, columns: {}, value_maps: {}, active: true };
    route(saved);
    const onMapping = vi.fn();
    renderIntl(<MappingStep source={source} fields={fields} mappings={[]} onMapping={onMapping} />);
    await waitFor(() => expect(screen.getByLabelText(/Objektnummer/)).toHaveValue("Objekt-Nr."));
    await userEvent.click(screen.getByLabelText(/Zuordnung für diesen Berichtstyp merken/));
    await userEvent.type(screen.getByLabelText("Name der Vorlage"), "Ohne");
    await userEvent.click(screen.getByRole("button", { name: /neue Vorlagenversion/ }));
    await waitFor(() => expect(onMapping).toHaveBeenCalledWith(saved));
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
  });

  it("runs the check report without saving and shows required columns and samples", async () => {
    route();
    renderIntl(<MappingStep source={source} fields={fields} mappings={[]} onMapping={vi.fn()} />);
    await waitFor(() => expect(screen.getByLabelText(/Objektnummer/)).toHaveValue("Objekt-Nr."));
    await userEvent.click(screen.getByRole("button", { name: "Prüfbericht erstellen" }));
    const report = await screen.findByTestId("column-check");
    expect(report).toHaveTextContent("2 Zeilen, davon 1 gültig und 1 fehlerhaft.");
    const post = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/check"))!;
    expect(JSON.parse(post[1].body as string)).toEqual({
      columns: { property_number: "Objekt-Nr.", number: "Einheit" },
      value_maps: {},
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/mappings"))).toBe(false);
  });

  it("renders the report with status per required column and error rows", () => {
    renderIntl(<ColumnCheckReport report={check} />);
    expect(screen.getByTestId("column-check-ready")).toHaveTextContent("Alle Pflichtspalten sind zugeordnet und gefüllt.");
    expect(screen.getByTestId("column-check-required")).toHaveTextContent("teilweise leer (1 Zeilen leer)");
    expect(screen.getByTestId("column-check-samples")).toHaveTextContent("001");
    expect(screen.getByTestId("column-check-errors")).toHaveTextContent("Einheitennummer: fehlt");
    expect(screen.getByText(/Nicht zugeordnete Spalten/)).toHaveTextContent("Bemerkung");
  });

  it("lists the export status per report type", async () => {
    const items: ExportRequirement[] = [
      { report_type: "properties", source: "Reports: Objektliste", required_fields: ["number", "name", "management_type"], optional_fields: [], stored_assignments: 1, required_covered: ["number"], files: 1, last_file_at: null, last_headers: 4, applied: false, status: "mapping_open" },
      { report_type: "journal", source: "Buchungen: Journal", required_fields: [], optional_fields: [], stored_assignments: 0, required_covered: [], files: 0, last_file_at: null, last_headers: null, applied: false, status: "file_missing" },
    ];
    fetchMock.mockImplementation(async () => jsonResponse(items));
    renderIntl(<ExportRequirements />);
    const table = await screen.findByTestId("export-requirements");
    expect(table).toHaveTextContent("Reports: Objektliste");
    expect(table).toHaveTextContent("1 von 3");
    expect(table).toHaveTextContent("Zuordnung offen");
    expect(table).toHaveTextContent("keine Zielfelder");
    expect(table).toHaveTextContent("Datei fehlt");
  });

  it("helpers keep file headers only and remember a header once", () => {
    expect(proposedColumns(proposal, ["Objekt-Nr."])).toEqual({ property_number: "Objekt-Nr." });
    expect(assignmentsFrom({ property_number: "A", number: "A", label: "" })).toEqual([{ header: "A", target_field: "property_number" }]);
  });
});
