import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { MeterChangesPanel, VacancyValuesPanel } from "./UnitPanels";

describe("VacancyValuesPanel", () => {
  it("shows the empty text without rows", () => {
    renderIntl(<VacancyValuesPanel rows={[]} />);
    expect(screen.getByText("Keine Leerstandswerte hinterlegt.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows name with code, falls back to the code and formats the dates", () => {
    renderIntl(
      <VacancyValuesPanel
        rows={[
          { id: "1", key_code: "PERS", key_name: "Personen", value: "1.00", valid_from: "2025-01-01", valid_to: "2025-12-31" },
          { id: "2", key_code: "QM", value: "2.50", valid_from: "2026-01-01" },
        ]}
      />,
    );
    expect(screen.getByText("Personen")).toBeInTheDocument();
    expect(screen.getByText("(PERS)")).toBeInTheDocument();
    expect(screen.getByText("QM")).toBeInTheDocument();
    expect(screen.getByText("01.01.2025")).toBeInTheDocument();
    expect(screen.getByText("31.12.2025")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });
});

describe("MeterChangesPanel", () => {
  it("shows the empty text without rows", () => {
    renderIntl(<MeterChangesPanel rows={[]} />);
    expect(screen.getByText("Keine Zählerwechsel erfasst.")).toBeInTheDocument();
  });

  it("falls back to the meter id and leaves the new number empty", () => {
    renderIntl(<MeterChangesPanel rows={[{ id: "1", meter_id: "meter-77", changed_on: "2025-06-30", old_number: "123", old_final_value: "455.5", new_initial_value: "0" }]} />);
    expect(screen.getByText("meter-77")).toBeInTheDocument();
    expect(screen.getByText("30.06.2025")).toBeInTheDocument();
    expect(screen.getByText("123")).toBeInTheDocument();
    expect(screen.getByTestId("unit-meter-changes")).toBeInTheDocument();
  });
});
