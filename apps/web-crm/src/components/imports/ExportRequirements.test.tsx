import { screen, within } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ExportRequirements } from "./ExportRequirements";

describe("ExportRequirements (GAI-615)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows coverage per report type, read only", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse([
        { report_type: "properties", source: "Objektliste", required_fields: ["a", "b", "c"], optional_fields: [], stored_assignments: 1, required_covered: ["a"], files: 2, last_file_at: null, status: "mapping_open" },
        { report_type: "units", source: "Einheiten", required_fields: [], optional_fields: [], stored_assignments: 0, required_covered: [], files: 0, last_file_at: null, status: "file_missing" },
      ]),
    );
    renderIntl(<ExportRequirements />);
    const table = await screen.findByTestId("export-requirements");
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(rows[1]).toHaveTextContent("Objekte");
    expect(rows[1]).toHaveTextContent("1 von 3");
    expect(rows[1]).toHaveTextContent("Zuordnung offen");
    expect(rows[2]).toHaveTextContent("keine Zielfelder");
    expect(rows[2]).toHaveTextContent("Datei fehlt");
    expect((fetchMock.mock.calls[0]![1] as RequestInit | undefined)?.method ?? "GET").toBe("GET");
  });

  it("shows the error and no table", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Fehler", status: 500 }, 500));
    renderIntl(<ExportRequirements />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByTestId("export-requirements")).not.toBeInTheDocument();
  });
});
