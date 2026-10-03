import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { LevyPaymentStatus, type LevyPaymentStatusData } from "./LevyPaymentStatus";

const DATA: LevyPaymentStatusData = {
  units: [
    {
      unit_id: "u1",
      unit_number: "01",
      charged: "2000.00",
      received: "1500.00",
      open: "500.00",
      refunds_proposed: "1000.00",
      instalments: [
        { due_month: "2026-03-01", charged: "2000.00", received: "1500.00", open: "500.00" },
        { due_month: "2026-04-01", charged: "0.00", received: "0.00", open: "0.00" },
      ],
    },
  ],
  usage: [{ journal_entry_id: "j1", booking_date: "2026-03-10", text: "Dachdecker", amount: "800.00" }],
  usage_truncated: true,
  note: "Hinweis W09",
};

describe("LevyPaymentStatus (AP21, GAM-110)", () => {
  it("shows charged, received and arrears per instalment and the use of funds", () => {
    renderIntl(<LevyPaymentStatus data={DATA} />);
    expect(screen.getByText("Zahlungsstand je Rate")).toBeInTheDocument();
    expect(screen.getByText("01.03.2026")).toBeInTheDocument();
    expect(screen.getAllByText(/500,00/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Erstattung vorgeschlagen/)).toBeInTheDocument();
    expect(screen.getByTestId("levy-usage")).toHaveTextContent("Dachdecker");
    expect(screen.getByText("Nur die ersten 200 Buchungen werden angezeigt.")).toBeInTheDocument();
    expect(screen.getByText("Hinweis W09")).toBeInTheDocument();
  });

  it("shows empty states", () => {
    renderIntl(<LevyPaymentStatus data={{ units: [], usage: [], usage_truncated: false, note: "" }} />);
    expect(screen.getByText("Noch keine Raten berechnet.")).toBeInTheDocument();
    expect(screen.getByText("Keine Buchungen auf dem Verwendungskonto.")).toBeInTheDocument();
  });
});
