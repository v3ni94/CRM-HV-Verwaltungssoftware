import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AiCostSummary, type AiCostSummaryOut } from "./AiCostSummary";

const summary: AiCostSummaryOut = {
  property_id: null,
  from: null,
  to: null,
  by_property: [
    { property_id: "p-1", property_number: "712", property_name: "Haus", calls: 3, tokens_in: 1000, tokens_out: 70, cost_eur: "1234.5678" },
    { property_id: null, property_number: null, property_name: null, calls: 1, tokens_in: 10, tokens_out: 1, cost_eur: "0.004" },
  ],
  by_month: [{ month: "2026-02", calls: 4, tokens_in: 1010, tokens_out: 71, cost_eur: "1234.5718" }],
  total: { calls: 4, tokens_in: 1010, tokens_out: 71, cost_eur: "1234.5718" },
};

describe("AiCostSummary", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads the summary and formats amounts as EUR", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(summary));
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<AiCostSummary properties={[{ id: "p-1", number: "712", name: "Haus" }]} />);
    await waitFor(() => expect(screen.getByTestId("ai-costs-by-property")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/bff/objektakte/ai-calls/summary");
    expect(screen.getByTestId("ai-costs-by-property")).toHaveTextContent("712 Haus");
    expect(screen.getByText("Ohne Objektzuordnung")).toBeInTheDocument();
    expect(screen.getAllByText("1.234,57 EUR")).toHaveLength(3);
    expect(screen.getByText("0,00 EUR")).toBeInTheDocument();
    expect(screen.getByText("02.2026")).toBeInTheDocument();
  });

  it("applies property and period filters as query parameters", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(summary))
      .mockResolvedValueOnce(jsonResponse({ ...summary, by_property: [], by_month: [], total: { calls: 0, tokens_in: 0, tokens_out: 0, cost_eur: "0.000000" } }));
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<AiCostSummary properties={[{ id: "p-1", number: "712", name: "Haus" }]} />);
    await waitFor(() => expect(screen.getByTestId("ai-costs-by-property")).toBeInTheDocument());

    await act(async () => {
      await userEvent.selectOptions(screen.getByLabelText("Objekt"), "p-1");
      await userEvent.type(screen.getByLabelText("Von"), "2026-03-01");
      await userEvent.type(screen.getByLabelText("Bis"), "2026-03-31");
      await userEvent.click(screen.getByRole("button", { name: "Auswerten" }));
    });
    await waitFor(() => expect(screen.getByText("Keine KI-Aufrufe im gewählten Zeitraum.")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe(
      "/api/bff/objektakte/ai-calls/summary?property_id=p-1&from=2026-03-01&to=2026-03-31",
    );
  });
});
