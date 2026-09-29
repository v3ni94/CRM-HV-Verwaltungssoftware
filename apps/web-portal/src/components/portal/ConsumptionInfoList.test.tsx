import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { ConsumptionInfoList, formatQuantity, monthLabel } from "./ConsumptionInfoList";
import type { ConsumptionInfoRow } from "./types";

const row: ConsumptionInfoRow = {
  id: "ci1",
  unit_id: "u1",
  month: "2025-08-01",
  values: {
    month: "2025-08-01",
    period_from: "2025-08-01",
    period_to: "2025-08-31",
    heating: { value: "123.5", unit_of_measure: "kWh", kind: "actual", source: "metering:test" },
    hot_water: { value: "2.4", unit_of_measure: "m3", kind: "estimated", source: "metering:test" },
    previous_month: { heating: { value: "80", unit_of_measure: "kWh", kind: "actual", source: "metering:test" }, hot_water: null },
    previous_year_month: null,
    property_average: { heating: { value: "123.50", units: 1, unit_of_measure: "kWh" }, hot_water: null },
  },
  estimated: ["hot_water"],
  created_at: "2025-09-01T05:40:00Z",
};

describe("ConsumptionInfoList", () => {
  it("renders month, figures in German format, estimated marking and missing values", () => {
    renderIntl(<ConsumptionInfoList rows={[row]} />);
    expect(screen.getByText("Verbrauchsinformation 08.2025")).toBeInTheDocument();
    expect(screen.getAllByText("123,50 kWh").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2,40 m3 (geschätzt)").length).toBeGreaterThan(0);
    expect(screen.getAllByText("80,00 kWh").length).toBeGreaterThan(0);
    expect(screen.getAllByText("keine Angabe").length).toBeGreaterThan(0);
    expect(screen.getByText(/Geschätzte Werte sind gekennzeichnet/)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Verbrauch je Monat 08.2025/ })).toBeInTheDocument();
    // Never any operator marker in the tenant view.
    expect(screen.queryByText(/verifizieren/)).not.toBeInTheDocument();
  });

  it("shows the empty notice and keeps the information note", () => {
    renderIntl(<ConsumptionInfoList rows={[]} />);
    expect(screen.getByText("Noch keine Verbrauchsinformation vorhanden.")).toBeInTheDocument();
    expect(screen.getByText(/Keine Abrechnung, keine Rechtsfolge/)).toBeInTheDocument();
  });

  it("formats quantities and months", () => {
    expect(formatQuantity(null, "geschätzt", "keine Angabe")).toBe("keine Angabe");
    expect(formatQuantity({ value: "1234.5", unit_of_measure: "kWh", kind: "actual", source: "x" }, "geschätzt", "keine Angabe")).toBe("1.234,50 kWh");
    expect(monthLabel("2026-01-01")).toBe("01.2026");
  });
});
