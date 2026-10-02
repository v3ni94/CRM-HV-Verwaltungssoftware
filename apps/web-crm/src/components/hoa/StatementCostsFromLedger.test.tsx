import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { StatementCostsFromLedger } from "./StatementCostsFromLedger";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const accounts = [{ id: "a1", number: "6000", name: "Wasser" }];
const keys = [{ id: "k1", name: "MEA" }];

async function fill() {
  const [acc, key] = screen.getAllByRole("combobox");
  await userEvent.selectOptions(acc!, "a1");
  await userEvent.selectOptions(key!, "k1");
  await userEvent.type(screen.getByRole("textbox"), "Beleg");
}

describe("StatementCostsFromLedger", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    refresh.mockClear();
  });

  it("validates before posting", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<StatementCostsFromLedger statementId="s1" accounts={accounts} keys={keys} />);
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts and shows created and skipped results", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ created: [{}, {}], skipped: [{ journal_entry_id: "j1", reason: "reversed" }] }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<StatementCostsFromLedger statementId="s1" accounts={accounts} keys={keys} />);
    await fill();
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/hoa/statements/s1/costs/from-ledger");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ account_id: "a1", allocation_key_id: "k1", basis: "Beleg" });
    expect(await screen.findByRole("status")).toHaveTextContent("2 Positionen übernommen.");
    expect(screen.getByText("storniert")).toBeInTheDocument();
  });

  it("shows 403 and no result", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<StatementCostsFromLedger statementId="s1" accounts={accounts} keys={keys} />);
    await fill();
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
