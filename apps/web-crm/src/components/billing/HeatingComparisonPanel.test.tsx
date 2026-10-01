import { fireEvent, screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HeatingComparisonPanel } from "./HeatingComparisonPanel";

describe("HeatingComparisonPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the comparison with tolerances and marks deviations", async () => {
    const urls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      urls.push(String(input));
      return jsonResponse({
        status: "berechnet",
        reason: null,
        rows: [
          { key: "k1", unit_number: "01", own: "1000.00", external: "900.00", difference: "100.00", percent: "11.11", status: "abweichung" },
          { key: "k2", unit_number: "02", own: "500.00", external: null, difference: null, percent: null, status: "extern_fehlt" },
        ],
        summary: { deviations: 1, missing_external: 1, method: "m" },
      });
    });
    renderIntl(<HeatingComparisonPanel id="s1" />);
    fireEvent.click(screen.getByRole("button", { name: "Vergleich laden" }));
    expect(await screen.findByText("Abweichung")).toBeInTheDocument();
    expect(screen.getByText("extern fehlt")).toBeInTheDocument();
    expect(urls[0]).toBe("/api/bff/statements/s1/heating/comparison?tolerance_abs=0.50&tolerance_percent=1.0");
    expect(screen.getByTestId("heating-compare").textContent).toMatch(/nichts gebucht/);
  });

  it("shows the reason when the own calculation is missing", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ status: "nicht_berechenbar", reason: "Eigene Heizkostenberechnung fehlt; erst berechnen.", rows: [], summary: { deviations: 0, missing_external: 0, method: "" } }),
    );
    renderIntl(<HeatingComparisonPanel id="s1" />);
    fireEvent.click(screen.getByRole("button", { name: "Vergleich laden" }));
    expect(await screen.findByText(/erst berechnen/)).toBeInTheDocument();
  });
});
