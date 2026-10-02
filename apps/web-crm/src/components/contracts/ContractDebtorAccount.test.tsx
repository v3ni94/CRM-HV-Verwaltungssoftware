import { screen, within } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { ContractDebtorAccount } from "./ContractDebtorAccount";

const ACCOUNT = { id: "a1", legal_entity_id: "e1", number: "10010", name: "Mustermann, Erika" };
const LEDGER = "0192abcd-0000-7000-8000-000000000051";

describe("ContractDebtorAccount", () => {
  it("shows the account and links to the open items of the creditor ledger", () => {
    renderIntl(
      <ContractDebtorAccount
        account={ACCOUNT}
        ledgerId={LEDGER}
        ledgerName="Buchungskreis HVM"
        moveInOn="2024-03-01"
        moveOutOn={null}
        readings={[]}
        meterLabels={{}}
      />,
    );
    const section = screen.getByTestId("contract-debtor-account");
    expect(within(section).getByText("10010")).toBeInTheDocument();
    expect(within(section).getByText("Mustermann, Erika")).toBeInTheDocument();
    expect(screen.getByTestId("open-items-link")).toHaveAttribute("href", `/buchhaltung/${LEDGER}`);
    expect(screen.getByTestId("open-items-link")).toHaveTextContent("Buchungskreis HVM");
    expect(within(section).getByText("01.03.2024")).toBeInTheDocument();
    expect(within(section).getByText("nicht erfasst")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("states that no ledger exists instead of linking", () => {
    renderIntl(
      <ContractDebtorAccount account={ACCOUNT} ledgerId={null} ledgerName={null} moveInOn={undefined} moveOutOn={undefined} readings={[]} meterLabels={{}} />,
    );
    expect(screen.queryByTestId("open-items-link")).not.toBeInTheDocument();
    expect(screen.getByText("Für den Gläubiger ist noch kein Buchungskreis angelegt.")).toBeInTheDocument();
  });

  it("lists termination meter readings with meter label or id fallback", () => {
    renderIntl(
      <ContractDebtorAccount
        account={ACCOUNT}
        ledgerId={LEDGER}
        ledgerName={null}
        moveInOn="2024-03-01"
        moveOutOn="2026-09-30"
        readings={[
          { id: "r1", meter_id: "m1", meter_reading_id: null, value: "123.456", read_at: "2026-09-30" },
          { id: "r2", meter_id: "m2", meter_reading_id: null, value: "7", read_at: "2026-09-30" },
        ]}
        meterLabels={{ m1: "Wasser Küche" }}
      />,
    );
    expect(screen.getByText("Wasser Küche: 123.456 (30.09.2026)")).toBeInTheDocument();
    expect(screen.getByText("m2: 7 (30.09.2026)")).toBeInTheDocument();
    expect(screen.getByTestId("open-items-link")).toHaveTextContent("Zum Buchungskreis");
  });
});
