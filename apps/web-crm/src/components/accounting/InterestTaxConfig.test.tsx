import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InterestTaxConfig } from "./InterestTaxConfig";
import type { LedgerAccountOption } from "./JournalEntryForm";

const acc = (id: string, number: string, category: string, active = true) => ({ id, number, name: `Konto ${number}`, category, active }) as unknown as LedgerAccountOption;
const accounts = [acc("a1", "1710", "liability"), acc("a2", "1200", "bank"), acc("a3", "1720", "liability", false)];
const URL = "/api/bff/accounting/ledgers/L1/interest-tax-config";
const empty = { capital_gains_tax_account_id: null, solidarity_tax_account_id: null, church_tax_account_id: null };

describe("InterestTaxConfig", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("offers only active non-bank accounts and saves the selection via PUT", async () => {
    const fetchMock = vi.fn<(u: string, i?: RequestInit) => Promise<Response>>(() => Promise.resolve(jsonResponse(empty)));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<InterestTaxConfig ledgerId="L1" accounts={accounts} />);
    const selects = await screen.findAllByRole("combobox");
    expect(selects).toHaveLength(3);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(URL);
    expect(screen.queryAllByRole("option", { name: /1200/ })).toHaveLength(0);
    expect(screen.queryAllByRole("option", { name: /1720/ })).toHaveLength(0);
    await userEvent.selectOptions(selects[0]!, "a1");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    const put = fetchMock.mock.calls.find((c) => c[1]?.method === "PUT");
    expect(JSON.parse(put?.[1]?.body as string)).toEqual({ ...empty, capital_gains_tax_account_id: "a1" });
    expect(await screen.findByRole("status")).toBeInTheDocument();
  });

  it("shows the error when saving is forbidden (403)", async () => {
    const fetchMock = vi.fn((_u: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "PUT" ? jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403) : jsonResponse(empty)),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<InterestTaxConfig ledgerId="L1" accounts={accounts} />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
