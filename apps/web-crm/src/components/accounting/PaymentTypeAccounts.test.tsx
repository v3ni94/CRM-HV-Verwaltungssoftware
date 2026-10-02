import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PaymentTypeAccounts } from "./PaymentTypeAccounts";

const accounts = [
  { id: "r1", number: "8400", name: "Erlöse", category: "revenue", active: true },
  { id: "t1", number: "1776", name: "Umsatzsteuer", category: "tax", active: true },
  { id: "r2", number: "8500", name: "Inaktiv", category: "revenue", active: false },
];
const URL = "/api/bff/accounting/ledgers/L1/payment-type-accounts";

describe("PaymentTypeAccounts", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("offers revenue accounts, tax accounts for vat_output, and saves via PUT", async () => {
    const fetchMock = vi.fn((_u: string, init?: RequestInit) => Promise.resolve(jsonResponse(init?.method === "PUT" ? {} : [])));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<PaymentTypeAccounts ledgerId="L1" accounts={accounts} />);
    const code = screen.getByRole("textbox");
    await userEvent.type(code, "rent");
    expect(screen.queryByRole("option", { name: /1776/ })).toBeNull();
    expect(screen.queryByRole("option", { name: /8500/ })).toBeNull();
    await userEvent.selectOptions(screen.getByRole("combobox"), "r1");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    const put = fetchMock.mock.calls.find((c) => c[1]?.method === "PUT");
    expect(put?.[0]).toBe(URL);
    expect(JSON.parse(put?.[1]?.body as string)).toEqual({ payment_type_code: "rent", account_id: "r1" });
    expect(await screen.findByTestId("payment-type-mappings")).toHaveTextContent("rent: 8400 Erlöse");
    await userEvent.clear(code);
    await userEvent.type(code, "vat_output");
    expect(screen.getByRole("option", { name: /1776/ })).toBeInTheDocument();
  });

  it("shows the error on 403", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_u: string, init?: RequestInit) =>
        Promise.resolve(init?.method === "PUT" ? jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403) : jsonResponse([])),
      ),
    );
    renderIntl(<PaymentTypeAccounts ledgerId="L1" accounts={accounts} />);
    await userEvent.type(screen.getByRole("textbox"), "rent");
    await userEvent.selectOptions(screen.getByRole("combobox"), "r1");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
