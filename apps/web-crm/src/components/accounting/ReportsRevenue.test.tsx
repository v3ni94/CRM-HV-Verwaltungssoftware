import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { RevenueReport } from "./ReportsRevenue";

describe("RevenueReport", () => {
  it("sums the amounts in cents without float drift", () => {
    renderIntl(
      <RevenueReport
        rows={[
          { number: "8400", name: "Erlöse", amount: "0.10" },
          { number: "8410", name: "Nebenerlöse", amount: "0.20" },
        ]}
      />,
    );
    expect(screen.getByTestId("revenue-total").textContent).toMatch(/0,30/);
    expect(screen.getByText("8400 Erlöse")).toBeInTheDocument();
  });

  it("shows the empty state without rows", () => {
    renderIntl(<RevenueReport rows={[]} />);
    expect(screen.queryByTestId("revenue-total")).toBeNull();
  });
});
