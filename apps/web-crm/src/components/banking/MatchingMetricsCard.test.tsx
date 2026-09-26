import { screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MatchingMetricsCard, formatRate } from "./MatchingMetricsCard";

const METRICS = {
  period_from: "2026-03-01",
  period_to: "2026-03-31",
  transactions: 5,
  incoming: 5,
  auto_matched: 2,
  manual_booked: 1,
  open: 1,
  ignored: 1,
  coverage: "0.4000",
  auto_reversed: 1,
  auto_corrected: 0,
  auto_cancelled: 1,
  error_rate: "0.5000",
  note: "Betriebskennzahlen.",
};

describe("MatchingMetricsCard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows coverage and error rate apart for the requested period", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(METRICS));
    renderIntl(<MatchingMetricsCard initialFrom="2026-03-01" initialTo="2026-03-31" />);
    expect(screen.getByRole("status")).toHaveTextContent("Kennzahlen werden geladen.");
    expect(await screen.findByTestId("metric-coverage")).toHaveTextContent("40,0 %");
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByTestId("metric-error-rate")).toHaveTextContent("50,0 %");
    expect(screen.getByText(/2 von 5/)).toBeInTheDocument();
    expect(screen.getByText(/1 von 2/)).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain("/api/bff/banking/matching-metrics?");
    expect(url).toContain("from=2026-03-01");
    expect(url).toContain("to=2026-03-31");
  });

  it("shows a placeholder without a base instead of a figure", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ ...METRICS, transactions: 0, auto_matched: 0, coverage: null, error_rate: null }),
    );
    renderIntl(<MatchingMetricsCard initialFrom="2030-01-01" initialTo="2030-01-31" />);
    expect(await screen.findByTestId("metric-coverage")).toHaveTextContent("keine Basis");
    expect(screen.getByTestId("metric-error-rate")).toHaveTextContent("keine Basis");
  });

  it("formats rates as German percentages", () => {
    expect(formatRate("0.4000", "-")).toBe("40,0 %");
    expect(formatRate("1", "-")).toBe("100,0 %");
    expect(formatRate(null, "-")).toBe("-");
  });
});
