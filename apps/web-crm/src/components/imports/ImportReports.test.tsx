import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ReconciliationView, RunReportView, ValidationReport } from "./ImportReports";

const ID = "01920000-0000-7000-8000-0000000000aa";
const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("ValidationReport", () => {
  it("shows counts, invalid rows with errors and filters by status", async () => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        jsonResponse(
          url.includes("status=invalid")
            ? [{ row_number: 5, raw: {}, values: null, status: "invalid", errors: ["Pflichtfeld fehlt: Objektnummer"], entity_type: null, entity_id: null }]
            : [],
        ),
      ),
    );
    renderIntl(<ValidationReport sourceId={ID} counts={{ valid: 12, invalid: 1 }} />);
    expect(screen.getByTestId("validation-counts")).toHaveTextContent("gültig12");
    expect(await screen.findByText("Pflichtfeld fehlt: Objektnummer")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]![0]).toBe(`/api/bff/imports/immoware24/files/${ID}/rows?limit=200&status=invalid`);
    await userEvent.selectOptions(screen.getByLabelText("Zeilen nach Status"), "valid");
    await waitFor(() => expect(fetchMock.mock.calls.at(-1)![0]).toContain("status=valid"));
    expect(await screen.findByText("Keine Zeilen.")).toBeInTheDocument();
  });
});

describe("RunReportView", () => {
  it("shows counts, problems and payment sums in German format", () => {
    renderIntl(
      <RunReportView
        report={{
          counts: { created: 3, conflict: 1 },
          problems: [{ row: 7, status: "conflict", messages: ["Vertrag nicht gefunden"] }],
          sums: { source_gross: "1234.5", created_gross: "1000" },
        }}
      />,
    );
    expect(screen.getByText("angelegt")).toBeInTheDocument();
    expect(screen.getByText("Vertrag nicht gefunden")).toBeInTheDocument();
    expect(screen.getByTestId("payment-sums")).toHaveTextContent("1.234,50 EUR");
    expect(screen.getByTestId("payment-sums")).toHaveTextContent("1.000,00 EUR");
  });
});

describe("ReconciliationView", () => {
  it("highlights unit differences per property and open differences", () => {
    renderIntl(
      <ReconciliationView
        data={{
          rows: 5,
          status: { created: 4, invalid: 1 },
          units_per_property: { "100": { file: 3, platform: 3, difference: 0 }, "200": { file: 2, platform: 1, difference: -1 } },
          open_differences: 1,
        }}
      />,
    );
    expect(screen.getByTestId("open-differences")).toHaveTextContent("1 offene Differenz");
    const rows = screen.getAllByRole("row");
    const diff = rows.filter((r) => r.getAttribute("data-difference") === "true");
    expect(diff).toHaveLength(1);
    expect(diff[0]).toHaveTextContent("200");
  });
});
