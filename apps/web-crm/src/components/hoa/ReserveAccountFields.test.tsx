import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { ReserveAccountFields } from "./ReserveAccountFields";

const bank = [{ id: "b1", label: "Rücklagenkonto WEG" }];
const accounts = [{ id: "a1", label: "1200 Rücklage" }];

describe("ReserveAccountFields", () => {
  it("lists bank and ledger accounts with the current selection", () => {
    renderIntl(<ReserveAccountFields bankAccounts={bank} accounts={accounts} bankAccountId="b1" accountId="" onBank={vi.fn()} onAccount={vi.fn()} />);
    const [bankSelect, accountSelect] = screen.getAllByRole("combobox") as [HTMLSelectElement, HTMLSelectElement];
    expect(bankSelect.value).toBe("b1");
    expect(accountSelect.value).toBe("");
    expect(screen.getByRole("option", { name: "1200 Rücklage" })).toBeInTheDocument();
  });

  it("reports the chosen ids to the parent", async () => {
    const onBank = vi.fn();
    const onAccount = vi.fn();
    renderIntl(<ReserveAccountFields bankAccounts={bank} accounts={accounts} bankAccountId="" accountId="" onBank={onBank} onAccount={onAccount} />);
    const [bankSelect, accountSelect] = screen.getAllByRole("combobox") as [HTMLElement, HTMLElement];
    await userEvent.selectOptions(bankSelect, "b1");
    await userEvent.selectOptions(accountSelect, "a1");
    expect(onBank).toHaveBeenCalledWith("b1");
    expect(onAccount).toHaveBeenCalledWith("a1");
  });
});
