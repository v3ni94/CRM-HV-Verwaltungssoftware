import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ReconciliationReports, type Report, type ReportSummary } from "./ReconciliationReports";

const ID = "01920000-0000-7000-8000-0000000000ab";
const API = "/api/bff/imports/reconciliation-reports";
const summary: ReportSummary = {
  id: ID,
  created_at: "2026-09-26T03:30:00Z",
  as_of: "2026-01-31",
  trigger: "beat",
  totals: { properties: 2, compared: 12, deviations: 5, missing_on_platform: 1 },
  sources: [{ id: "s1", report_type: "journal", row_count: 9 }],
};
const report: Report = {
  ...summary,
  counts: { journal: 7 },
  warnings: ["journal Zeile 10: Objektnummer fehlt"],
  properties: [],
  lines: [
    { property_number: "851", metric: "kontosaldo", key: "001200", source: "200.00", platform: "200.00", difference: "0.00", deviates: false, hint: null },
    { property_number: "851", metric: "kontosaldo", key: "060100", source: "-310.00", platform: "-300.00", difference: "10.00", deviates: true, hint: null },
    { property_number: "851", metric: "bankstand", key: "2051", source: "10150.00", platform: "10200.00", difference: "50.00", deviates: true, hint: null },
    { property_number: "999", metric: "kontosaldo", key: "001200", source: "1.00", platform: null, difference: null, deviates: true, hint: "Objekt nicht auf der Plattform" },
  ],
};

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("ReconciliationReports", () => {
  it("lists reports, opens a report with German amounts and filters deviations", async () => {
    fetchMock.mockImplementation((url: string) => Promise.resolve(jsonResponse(url === API ? [summary] : report)));
    renderIntl(<ReconciliationReports canCreate={false} />);
    const row = await screen.findByTestId("reconciliation-row");
    expect(row).toHaveTextContent("täglicher Lauf");
    expect(row).toHaveTextContent("31.01.2026");
    expect(screen.queryByTestId("reconciliation-create")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "CSV herunterladen" })).toHaveAttribute("href", `${API}/${ID}/csv`);

    await userEvent.click(screen.getByRole("button", { name: /26\.09\.2026/ }));
    expect(fetchMock.mock.calls.at(-1)![0]).toBe(`${API}/${ID}`);
    await screen.findByTestId("reconciliation-detail");
    expect(screen.getByTestId("reconciliation-totals")).toHaveTextContent("Abweichungen5");
    expect(screen.getByTestId("reconciliation-warnings")).toHaveTextContent("1 Rohzeile konnte nicht gelesen werden");
    // Only deviations by default: 3 of 4 lines, amounts in 1.234,56 EUR format.
    const lines = screen.getByTestId("reconciliation-lines");
    expect(lines.querySelectorAll("tbody tr")).toHaveLength(3);
    expect(lines).toHaveTextContent("-310,00 EUR");
    expect(lines).toHaveTextContent("10.150,00 EUR");
    expect(lines).toHaveTextContent("50,00 EUR");
    expect(lines).toHaveTextContent("Bankstand");
    expect(lines).toHaveTextContent("nicht vorhanden");
    expect(lines).toHaveTextContent("Objekt nicht auf der Plattform");
    await userEvent.click(screen.getByLabelText("Nur Abweichungen anzeigen"));
    expect(screen.getByTestId("reconciliation-lines").querySelectorAll("tbody tr")).toHaveLength(4);
  });

  it("creates a report on demand with the chosen date and shows errors", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse({ ...report, trigger: "manual" }, 201))
      .mockResolvedValueOnce(jsonResponse([{ ...summary, trigger: "manual" }]));
    renderIntl(<ReconciliationReports canCreate />);
    expect(await screen.findByTestId("reconciliation-empty")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Stichtag"), "2026-01-31");
    await userEvent.click(screen.getByTestId("reconciliation-create"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [url, init] = fetchMock.mock.calls[1]!;
    expect(url).toBe(API);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ as_of: "2026-01-31" });
    expect(await screen.findByTestId("reconciliation-detail")).toHaveTextContent("manuell");
    expect(screen.getByTestId("reconciliation-row")).toBeInTheDocument();

    fetchMock.mockResolvedValueOnce(jsonResponse({ code: "MHVP-CORE-0004", detail: "Keine Rohzeilen (Journal oder Bankumsätze) zum Abgleich vorhanden." }, 422));
    await userEvent.click(screen.getByTestId("reconciliation-create"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Keine Rohzeilen");
  });
});

describe("ReconciliationReports loading state (review 26.09.2026)", () => {
  it("ends the loading state and shows the error when the list cannot be loaded", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ title: "Nicht erreichbar", status: 503 }, 503));
    renderIntl(<ReconciliationReports canCreate={false} />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Nicht erreichbar"));
    expect(screen.queryByText("Berichte werden geladen.")).not.toBeInTheDocument();
    expect(screen.getByTestId("reconciliation-empty")).toBeInTheDocument();
  });
});
