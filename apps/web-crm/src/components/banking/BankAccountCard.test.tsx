import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { BankAccountCard } from "./BankAccountCard";
import type { BankAccountOption } from "./bankAccountTypes";

const base: BankAccountOption = {
  id: "a1",
  property_id: "p1",
  property_number: "100",
  property_name: "Musterstraße",
  legal_entity_id: "le1",
  legal_entity_name: "WEG Musterstraße",
  legal_entity_kind: "weg",
  kind: "hoa",
  iban_masked: "DE** **** 1234",
  bic: null,
  bank_name: "Testbank",
  holder: "WEG Musterstraße",
  valid_from: "2026-01-01",
  valid_to: null,
  source: "manual",
  balance: "1234.50",
  balance_as_of: "2026-09-30",
  balance_source: "statement",
  default_for_legal_entity: true,
  assignments: [],
  recent_transactions: [],
};

describe("BankAccountCard", () => {
  it("shows the balance with source and an empty transaction hint", () => {
    renderIntl(<BankAccountCard account={base} />);
    expect(screen.getByTestId("bank-account-card")).toBeInTheDocument();
    expect(screen.getByText(/1\.234,50/)).toBeInTheDocument();
    expect(screen.getByText("laut Kontoauszug")).toBeInTheDocument();
    expect(screen.getByText("Keine Umsätze vorhanden.")).toBeInTheDocument();
  });

  it("shows the unknown balance text and the recent transactions", () => {
    renderIntl(
      <BankAccountCard
        account={{
          ...base,
          balance: null,
          balance_source: null,
          balance_as_of: null,
          recent_transactions: [{ id: "t1", booking_date: "2026-09-29", amount: "-20.00", counterpart_name: "Stadtwerke", purpose: "Abschlag" }],
        }}
      />,
    );
    expect(screen.getByText("Kein Kontostand bekannt")).toBeInTheDocument();
    expect(screen.getByText(/Stadtwerke/)).toBeInTheDocument();
    expect(screen.getByText(/20,00/)).toBeInTheDocument();
  });
});
