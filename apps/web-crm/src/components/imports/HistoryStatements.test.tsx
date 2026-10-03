import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HistoryStatements } from "./HistoryStatements";

const props = [{ property_id: "P1", property_number: "851", property_name: "Musterstr." }];
const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("HistoryStatements", () => {
  it("loads statements, resolutions and the check report", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/statements/check")) {
        return Promise.resolve(
          jsonResponse({
            totals: { statements: 1, resolutions: 1, findings: 1 },
            properties: [],
            findings: [{ property_number: "851", entity: "statement", entity_id: "S1", code: "no_document", message: "Beleg fehlt" }],
          }),
        );
      }
      if (url.includes("/statements")) {
        return Promise.resolve(
          jsonResponse([{ id: "S1", kind: "hoa_annual", period_start: "2024-01-01", period_end: "2024-12-31", version: 1, unit_number: "01", recipient: "Muster", result_amount: "-1234.50", sent_on: null }]),
        );
      }
      return Promise.resolve(jsonResponse([{ id: "R1", resolved_on: "2024-05-01", item_number: "3", title: "Wirtschaftsplan", result: "angenommen", form: "Versammlung" }]));
    });
    renderIntl(<HistoryStatements properties={props} />);
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), "P1");
    await userEvent.click(screen.getByRole("button", { name: "Laden" }));
    expect(await screen.findByTestId("history-check")).toHaveTextContent("1 Prüfhinweise");
    expect(screen.getByTestId("history-check")).toHaveTextContent("Beleg fehlt");
    expect(screen.getByTestId("history-statements")).toHaveTextContent("-1.234,50 EUR");
    expect(screen.getByTestId("history-statements")).toHaveTextContent("Jahresabrechnung WEG");
    expect(screen.getByTestId("history-resolutions")).toHaveTextContent("Wirtschaftsplan");
    expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("property_id=P1"))).toBe(true);
  });

  it("shows empty states", async () => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(jsonResponse(url.includes("/check") ? { totals: { statements: 0, resolutions: 0, findings: 0 }, properties: [], findings: [] } : [])),
    );
    renderIntl(<HistoryStatements properties={props} />);
    await userEvent.click(screen.getByRole("button", { name: "Laden" }));
    expect(await screen.findByText("Keine Altabrechnungen übernommen.")).toBeInTheDocument();
    expect(screen.getByText("Keine Beschlüsse übernommen.")).toBeInTheDocument();
    expect(screen.getByText("Keine Prüfhinweise.")).toBeInTheDocument();
  });
});
