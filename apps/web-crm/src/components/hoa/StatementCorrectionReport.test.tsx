import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { StatementCorrectionReport, type CorrectionReport } from "./StatementCorrectionReport";

const t = (o: string, n: string, d: string) => ({ old: o, new: n, difference: d });
const report: CorrectionReport = {
  old: { version: 1 },
  new: { version: 2 },
  owners: [
    { owner: "Erika Beispiel", units: ["WE 01", "WE 02"], cost_share: t("10.00", "15.00", "5.00"), advances_resolved: t("0.00", "0.00", "0.00"), result: t("-10.00", "-15.00", "-5.00") },
  ],
  correction: { reason: "Rechenfehler", basis: "Beschluss", legal_note: "Hinweis" },
};

describe("StatementCorrectionReport", () => {
  it("shows versions, reason and the owner row with the result difference", () => {
    renderIntl(<StatementCorrectionReport report={report} />);
    expect(screen.getByRole("heading", { level: 2 }).textContent).toMatch(/V1 \/ V2/);
    expect(screen.getByText(/Rechenfehler/)).toBeInTheDocument();
    const row = screen.getByText("Erika Beispiel").closest("tr")!;
    expect(row.textContent).toContain("WE 01, WE 02");
    expect(row.textContent).toMatch(/5,00/);
  });

  it("shows the no-owners hint and the heating table when present", () => {
    renderIntl(
      <StatementCorrectionReport
        report={{
          old: { version: 1 },
          new: { version: 2 },
          owners: [],
          heating: { old: { cost_booked: "10.00" }, new: { cost_booked: "12.00" }, difference: { cost_booked: "2.00" } } as never,
        }}
      />,
    );
    expect(screen.queryByText("Erika Beispiel")).toBeNull();
    expect(screen.getAllByRole("table")).toHaveLength(1);
    expect(screen.getByText(/12,00/)).toBeInTheDocument();
  });
});
