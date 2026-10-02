import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AccountAllocationEditor, sumBasisPoints } from "./AccountAllocationEditor";

const keys = [{ id: "k1", code: "MEA", name: "Miteigentum" }, { id: "k2", code: "QM", name: "Fläche" }];
const URL = "/api/bff/accounting/ledgers/L1/accounts/A1/allocations";
const out = { items: [{ allocation_key_id: "k1", share_percent: "60.0000" }, { allocation_key_id: "k2", share_percent: "40.0000" }], total_percent: "100.0000" };

describe("AccountAllocationEditor", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sums percentages without float drift", () => {
    expect(sumBasisPoints(["33,3333", "33,3333", "33,3334"])).toBe(1_000_000);
    expect(sumBasisPoints(["0.1", "0.2"])).toBe(3000);
  });

  it("loads the rows and saves a valid 100 percent split via PUT", async () => {
    const fetchMock = vi.fn<(u: string, i?: RequestInit) => Promise<Response>>(() => Promise.resolve(jsonResponse(out)));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<AccountAllocationEditor ledgerId="L1" accountId="A1" keys={keys} canUpdate />);
    expect(await screen.findAllByRole("combobox")).toHaveLength(2);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(URL);
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: /speichern/i }));
    });
    const put = fetchMock.mock.calls.find((c) => c[1]?.method === "PUT");
    expect(JSON.parse(put?.[1]?.body as string)).toEqual({
      items: [{ allocation_key_id: "k1", share_percent: "60" }, { allocation_key_id: "k2", share_percent: "40" }],
    });
    expect(await screen.findByRole("status")).toBeInTheDocument();
  });

  it("blocks saving when the total is not 100 percent", async () => {
    vi.stubGlobal("fetch", vi.fn<(u: string, i?: RequestInit) => Promise<Response>>(() => Promise.resolve(jsonResponse(out))));
    renderIntl(<AccountAllocationEditor ledgerId="L1" accountId="A1" keys={keys} canUpdate />);
    const shares = await screen.findAllByRole("textbox");
    await userEvent.clear(shares[1]!);
    await userEvent.type(shares[1]!, "30");
    expect(screen.getByRole("button", { name: /speichern/i })).toBeDisabled();
  });

  it("is read only without update permission", async () => {
    vi.stubGlobal("fetch", vi.fn<(u: string, i?: RequestInit) => Promise<Response>>(() => Promise.resolve(jsonResponse(out))));
    renderIntl(<AccountAllocationEditor ledgerId="L1" accountId="A1" keys={keys} canUpdate={false} />);
    const shares = await screen.findAllByRole("textbox");
    expect(shares[0]).toBeDisabled();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows the load error (403)", async () => {
    vi.stubGlobal("fetch", vi.fn<(u: string, i?: RequestInit) => Promise<Response>>(() => Promise.resolve(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403))));
    renderIntl(<AccountAllocationEditor ledgerId="L1" accountId="A1" keys={keys} canUpdate />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
