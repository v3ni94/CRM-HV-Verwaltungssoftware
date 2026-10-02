import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { HoaAccountTable, formatEur, runningBalances } from "./HoaAccountTable";
import type { HoaAccount, HoaAccountEntry } from "./types";

const entry = (direction: "charge" | "credit", amount: string, extra: Partial<HoaAccountEntry> = {}): HoaAccountEntry => ({
  booking_date: "2026-03-01",
  due_date: null,
  text: "Hausgeld",
  kind: "x",
  direction,
  amount,
  reversed: false,
  ...extra,
});

describe("runningBalances and formatEur", () => {
  it("adds charges, subtracts credits and avoids float drift", () => {
    expect(runningBalances([entry("charge", "0.10"), entry("charge", "0.20"), entry("credit", "0.05")])).toEqual(["0.10", "0.30", "0.25"]);
  });

  it("formats amounts as 1.234,56 EUR", () => {
    expect(formatEur("1234.5")).toBe("1.234,50 EUR");
  });
});

describe("HoaAccountTable", () => {
  it("always shows the API note and an empty notice without contracts", () => {
    renderIntl(<HoaAccountTable account={{ note: "Hinweis der Verwaltung", legacy_note: null, contracts: [] } as unknown as HoaAccount} />);
    expect(screen.getByText("Hinweis der Verwaltung")).toBeInTheDocument();
  });

  it("renders booking dates, amounts and the balance with the owed marker", () => {
    const account = {
      note: "Hinweis",
      legacy_note: null,
      contracts: [
        {
          contract_number: "V-1",
          entries: [entry("charge", "250.00", { text: "Hausgeld März" }), entry("credit", "100.00", { text: "Zahlung" })],
          charges: "250.00",
          credits: "100.00",
          balance: "150.00",
          note: null,
        },
      ],
    } as unknown as HoaAccount;
    renderIntl(<HoaAccountTable account={account} />);
    expect(screen.getByRole("heading", { level: 2 }).textContent).toContain("V-1");
    expect(screen.getAllByText("Hausgeld März").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/01\.03\.2026/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("150,00 EUR").length).toBeGreaterThan(0);
    expect(screen.getByTestId("hoa-cards").querySelectorAll("li")).toHaveLength(2);
  });
});
