import { screen, within } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { SubledgerCheck, type SubledgerRow } from "./SubledgerCheck";

const row = (over: Partial<SubledgerRow>): SubledgerRow => ({
  account_id: "a1",
  number: "70001",
  name: "Mieter A",
  category: "debtor",
  ledger_balance: "250.00",
  open_items_remaining: "250.00",
  difference: "0.00",
  ...over,
});

describe("SubledgerCheck", () => {
  it("splits debtors and creditors and marks a difference with the cut-off date", () => {
    renderIntl(
      <SubledgerCheck
        asOf="2026-09-30"
        rows={[
          row({}),
          row({ account_id: "a2", number: "70002", name: "Mieter B", ledger_balance: "-50.00", open_items_remaining: "0.00", difference: "-50.00" }),
          row({ account_id: "c1", number: "80001", name: "Lieferant", category: "creditor", ledger_balance: "-100.00", open_items_remaining: "-100.00" }),
        ]}
      />,
    );
    expect(screen.getByText(/30\.09\.2026/)).toBeInTheDocument();
    expect(screen.getByTestId("subledger-summary").textContent).toMatch(/1/);
    const debtors = screen.getByTestId("subledger-debtor");
    expect(within(debtors).getAllByRole("row")).toHaveLength(3);
    const marked = debtors.querySelector('tr[data-difference="yes"]');
    expect(marked?.textContent).toMatch(/70002/);
    expect(marked?.textContent).toMatch(/50,00/);
    const creditors = screen.getByTestId("subledger-creditor");
    expect(within(creditors).getByText(/80001/)).toBeInTheDocument();
    expect(creditors.querySelector('tr[data-difference="yes"]')).toBeNull();
  });

  it("shows empty sections and no difference notice without accounts", () => {
    renderIntl(<SubledgerCheck asOf="2026-09-30" rows={[]} />);
    expect(screen.getByTestId("subledger-summary").textContent).toMatch(/Keine Differenz/);
    expect(screen.getAllByText(/Keine Konten/)).toHaveLength(2);
  });

  it("names written off and reversed items that are not counted", () => {
    renderIntl(
      <SubledgerCheck
        asOf="2026-09-30"
        rows={[row({})]}
        excluded={{
          exclude_written_off: true,
          written_off: { count: 2, amount: "80.00" },
          reversed: { count: 1, amount: "100.00" },
        }}
      />,
    );
    const note = screen.getByTestId("subledger-excluded").textContent ?? "";
    expect(note).toMatch(/2 ausgebuchte/);
    expect(note).toMatch(/1 stornierter/);
    expect(note).toMatch(/nicht gezählt/);
  });

  it("states that items are included when the switch is off", () => {
    renderIntl(
      <SubledgerCheck
        asOf="2026-09-30"
        rows={[row({})]}
        excluded={{
          exclude_written_off: false,
          written_off: { count: 1, amount: "5.00" },
          reversed: { count: 0, amount: "0.00" },
        }}
      />,
    );
    expect(screen.getByTestId("subledger-excluded").textContent).toMatch(/enthalten/);
  });
});
