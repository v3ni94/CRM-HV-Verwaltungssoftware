import { render, screen, within } from "@testing-library/react";
import { createTranslator } from "next-intl";


import { ReserveDevelopment, type ReserveBlock } from "./ReserveDevelopment";

vi.mock("next-intl/server", async () => {
  const messages = (await import("../../../messages/de.json")).default;
  return { getTranslations: async (ns: string) => createTranslator({ locale: "de", messages, namespace: ns as never }) };
});


const block: ReserveBlock = {
  opening: "1000.00",
  contributions_resolved: "500.00",
  contributions_paid: "400.00",
  contributions_paid_unassigned: "25.00",
  withdrawals: "100.00",
  interest: "5.00",
  closing: "1305.00",
  bank_balance: "1305.00",
  bank_difference: "0.00",
  positions: [
    {
      reserve_id: "r1",
      name: "Dachrücklage",
      purpose: "Dach",
      contributions_planned: "500.00",
      contributions_paid: "400.00",
      contributions_paid_bound: false,
      withdrawals: "100.00",
      taxes: "0.00",
      fees: "0.00",
      interest: "5.00",
      planned_change: "405.00",
      paid_change: "305.00",
      movements: [],
    },
  ],
};

describe("ReserveDevelopment", () => {
  it("renders totals, the unassigned notice and the position with planned change when unbound", async () => {
    render(await ReserveDevelopment({ block }));
    expect(screen.getByTestId("reserve-development")).toBeInTheDocument();
    expect(screen.getByText(/25,00/)).toBeInTheDocument();
    const row = within(screen.getByTestId("reserve-positions")).getByText("Dachrücklage").closest("tr")!;
    expect(row.textContent).toMatch(/405,00/);
    expect(row.textContent).not.toMatch(/305,00/);
  });

  it("uses the paid change when the contributions are bound and hides empty extras", async () => {
    const bound = { ...block, contributions_paid_unassigned: "0.00", positions: [{ ...block.positions![0]!, contributions_paid_bound: true }] };
    render(await ReserveDevelopment({ block: bound }));
    const row = screen.getByText("Dachrücklage").closest("tr")!;
    expect(row.textContent).toMatch(/305,00/);
    expect(screen.queryByText(/25,00/)).toBeNull();
  });

  it("omits the positions table without positions", async () => {
    render(await ReserveDevelopment({ block: { ...block, positions: undefined } }));
    expect(screen.queryByTestId("reserve-positions")).toBeNull();
  });

  it("shows open contributions as own row and explains a bank difference (GAM-104)", async () => {
    render(await ReserveDevelopment({ block: { ...block, bank_difference: "-100.00" } }));
    const row = screen.getByText("Offene Beiträge (nicht verfügbare Liquidität)").closest("tr")!;
    expect(row.textContent).toMatch(/100,00/);
    expect(screen.getByTestId("reserve-bank-difference-note")).toBeInTheDocument();
  });

  it("shows no note without a bank difference and a negative open amount exactly", async () => {
    render(await ReserveDevelopment({ block: { ...block, contributions_resolved: "400.00", contributions_paid: "400.10" } }));
    expect(screen.queryByTestId("reserve-bank-difference-note")).toBeNull();
    expect(screen.getByText("Offene Beiträge (nicht verfügbare Liquidität)").closest("tr")!.textContent).toMatch(/-0,10/);
  });
});
