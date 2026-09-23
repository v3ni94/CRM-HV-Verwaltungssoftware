import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { OpenItemsTable } from "./OpenItemsTable";

describe("OpenItemsTable", () => {
  it("sums the remaining amounts in cents", () => {
    renderIntl(
      <OpenItemsTable
        rows={[
          { id: "1", account_number: "10001", kind: "receivable", due_date: "2026-03-03", amount: "300.00", remaining: "0.10" },
          { id: "2", account_number: "10002", kind: "receivable", due_date: "2026-03-03", amount: "50.00", remaining: "0.20" },
        ]}
      />,
    );
    expect(screen.getByTestId("open-total").textContent).toMatch(/0,30\s€|0,30\sEUR/);
  });
});
