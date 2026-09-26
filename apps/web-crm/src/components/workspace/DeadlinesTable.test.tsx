import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { DeadlinesTable, type Deadline } from "./DeadlinesTable";

const row: Deadline = {
  id: "01920000-0000-7000-8000-0000000000cc",
  kind: "meter_calibration",
  source_type: "meter",
  source_id: "01920000-0000-7000-8000-0000000000dd",
  reference: "Zähler 4711 (901 Testhaus)",
  due_on: "2026-10-16",
  lead_days: 30,
  status: "open",
  property_id: null,
  notified_at: "2026-09-26T18:00:00Z",
  done_at: null,
  updated_at: "2026-09-26T18:00:00Z",
};

describe("DeadlinesTable", () => {
  it("renders the empty state", () => {
    renderIntl(<DeadlinesTable rows={[]} />);
    expect(screen.getByText("Keine Fristen im gewählten Zeitraum.")).toBeInTheDocument();
  });

  it("renders rows with German labels, dates and the verification badge", () => {
    renderIntl(<DeadlinesTable rows={[row]} />);
    expect(screen.getByText("Eichfrist Zähler")).toBeInTheDocument();
    expect(screen.getByText("16.10.2026")).toBeInTheDocument();
    expect(screen.getByText("30 Tage")).toBeInTheDocument();
    expect(screen.getByText("offen")).toBeInTheDocument();
    expect(screen.getByText("zu prüfen")).toBeInTheDocument();
    expect(screen.getByText("26.09.2026")).toBeInTheDocument();
  });
});
