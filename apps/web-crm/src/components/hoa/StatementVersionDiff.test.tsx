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

  it("shows the correction report per owner and the heating bridge (P02, D09)", () => {
    renderIntl(
      <StatementVersionDiff
        diff={{
          old: { id: "a", version: 1 },
          new: { id: "b", version: 2 },
          total_costs: tr("8000.00", "8000.00", "0.00"),
          units: [],
          positions: [],
          owners: [{ owner: "p1", units: ["01"], cost_share: tr("3000.00", "3272.73", "272.73"), advances_resolved: tr("2800.00", "2800.00", "0.00"), result: tr("200.00", "472.73", "272.73") }],
          heating: {
            old: { cash_outflows: "10000.00", cost_distributed: "8000.00", heating_accrual: "0.00", unexplained: "-2000.00" },
            new: { cash_outflows: "10000.00", cost_distributed: "8000.00", heating_accrual: "-2000.00", unexplained: "0.00" },
            difference: { cash_outflows: "0.00", cost_distributed: "0.00", heating_accrual: "-2000.00", unexplained: "2000.00" },
          },
          correction: { reason: "other", basis: null, legal_note: "Rechtsfolge der Korrektur offen (P02)." },
        }}
      />,
    );
    expect(screen.getByTestId("correction-owners")).toHaveTextContent("3.272,73");
    expect(screen.getByTestId("correction-heating")).toHaveTextContent("Unerklärte Differenz");
    expect(screen.getByTestId("correction-heating")).toHaveTextContent("10.000,00");
    expect(screen.getByText("Rechtsfolge der Korrektur offen (P02).")).toBeInTheDocument();
  });
});
