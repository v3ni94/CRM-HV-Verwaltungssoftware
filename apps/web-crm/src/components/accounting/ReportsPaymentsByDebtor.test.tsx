import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { PaymentsByDebtor } from "./ReportsPaymentsByDebtor";

describe("PaymentsByDebtor", () => {
  it("shows the empty state when nothing was settled", () => {
    renderIntl(<PaymentsByDebtor rows={[]} />);
    expect(screen.getByText(/Keine Zahlungseingänge/)).toBeInTheDocument();
  });

  it("sums the settled amounts and renders a card fallback for phones", () => {
    renderIntl(
      <PaymentsByDebtor
        rows={[
          { number: "70001", name: "Eigentümer A", settled: "100.10" },
          { number: "70002", name: "Eigentümer B", settled: "50.20" },
        ]}
      />,
    );
    expect(screen.getByTestId("payments-by-debtor-total").textContent).toMatch(/150,30/);
    expect(screen.getByTestId("payments-by-debtor-cards")).toBeInTheDocument();
  });
});
