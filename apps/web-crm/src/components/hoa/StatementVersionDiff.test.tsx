import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { StatementVersionDiff, type DiffTriple } from "./StatementVersionDiff";

const tr = (o: string, n: string, d: string): DiffTriple => ({ old: o, new: n, difference: d });

describe("StatementVersionDiff", () => {
  it("shows D14 values per unit and per cost position with German amounts", () => {
    renderIntl(
      <StatementVersionDiff
        diff={{
          old: { id: "a", version: 1 },
          new: { id: "b", version: 2 },
          total_costs: tr("5500.00", "5600.00", "100.00"),
          units: [
            { unit_number: "01", in_old: true, in_new: true, cost_share: tr("3000.00", "3054.55", "54.55"), advances_resolved: tr("2800.00", "2800.00", "0.00"), result: tr("200.00", "254.55", "54.55"), arrears: tr("300.00", "300.00", "0.00") },
            { unit_number: "02", in_old: true, in_new: true, cost_share: tr("2500.00", "2545.45", "45.45"), advances_resolved: tr("2800.00", "2800.00", "0.00"), result: tr("-300.00", "-254.55", "45.45"), arrears: tr("300.00", "300.00", "0.00") },
          ],
          positions: [
            { label: "Bewirtschaftung", in_old: true, in_new: true, amount: tr("5500.00", "5500.00", "0.00"), split: {} },
            { label: "Nachtrag", in_old: false, in_new: true, amount: tr("0", "100.00", "100.00"), split: {} },
          ],
        }}
      />,
    );
    const section = screen.getByTestId("statement-version-diff");
    expect(section).toHaveTextContent("Versionsvergleich V1 zu V2");
    expect(section).toHaveTextContent("3.054,55");
    expect(section).toHaveTextContent("2.545,45");
    expect(section).toHaveTextContent("54,55");
    expect(section).toHaveTextContent("Position: Nachtrag (nur in neuer Version)");
    expect(screen.getByText("Einheit 01: Kostenanteil")).toBeInTheDocument();
    expect(screen.getByText("Einheit 02: Spitze / Anpassung")).toBeInTheDocument();
  });
});
