import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { VacancyTable } from "./VacancyTable";

describe("VacancyTable", () => {
  it("shows vacancy start, days and area; unknown start stays unknown", () => {
    renderIntl(
      <VacancyTable
        rows={[
          { unit_id: "u1", property_number: "761", unit_number: "02", unit_type: "apartment", living_area_sqm: "60.00000000", vacant_since: "2026-07-01", vacant_days: 85 },
          { unit_id: "u2", property_number: "761", unit_number: "03", unit_type: "apartment", living_area_sqm: null, vacant_since: null, vacant_days: null },
        ]}
      />,
    );
    expect(screen.getByText("01.07.2026")).toBeInTheDocument();
    expect(screen.getByText("85")).toBeInTheDocument();
    expect(screen.getByText("60,00 m²")).toBeInTheDocument();
    expect(screen.getAllByText("unbekannt").length).toBe(3);
  });
});
