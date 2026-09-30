import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AccountAllocationEditor, sumBasisPoints } from "./AccountAllocationEditor";
import { EntryActions } from "./EntryActions";
import { JournalEntryForm, sumCents, toDecimal } from "./JournalEntryForm";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const L = "0192abcd-0000-7000-8000-000000000001";
const accounts = [
  { id: "a1", number: "060100", name: "Hausmeister", category: "cost", active: true },
  { id: "a2", number: "060200", name: "Reinigung", category: "cost", active: true },
  { id: "b1", number: "001200", name: "Bank", category: "bank", active: true },
];

describe("bookkeeping helpers", () => {
  it("parses German decimals and sums exactly in cents", () => {
    expect(toDecimal("1.234,56")).toBe("1234.56");
    expect(toDecimal("")).toBe("0");
    expect(sumCents(["0,10", "0,20"])).toBe(30);
    expect(sumBasisPoints(["33,3333", "66,6667"])).toBe(1_000_000);
  });
});

describe("JournalEntryForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("refuses an unbalanced entry without calling the API", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    renderIntl(<JournalEntryForm ledgerId={L} accounts={accounts} today="2026-03-01" />);
    await userEvent.type(screen.getByLabelText("Buchungstext"), "Test");
    const debit = screen.getAllByLabelText("Soll");
    const credit = screen.getAllByLabelText("Haben");
    await userEvent.type(debit[0]!, "10");
    await userEvent.type(credit[1]!, "9");
    await userEvent.click(screen.getByText("Entwurf speichern"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Soll und Haben");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("sends a cost transfer to the dedicated endpoint", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ id: "e1" }, 201));
    renderIntl(<JournalEntryForm ledgerId={L} accounts={accounts} today="2026-03-01" />);
    await userEvent.selectOptions(screen.getByLabelText("Vorgang"), "cost_transfer");
    await userEvent.type(screen.getByLabelText("Buchungstext"), "Fehlkontierung");
    await userEvent.selectOptions(screen.getByLabelText("Von Kostenkonto"), "a1");
    await userEvent.selectOptions(screen.getByLabelText("Auf Kostenkonto"), "a2");
    await userEvent.type(screen.getByLabelText("Betrag in EUR"), "120,00");
    await userEvent.click(screen.getByText("Entwurf speichern"));
    expect(await screen.findByRole("status")).toBeInTheDocument();
    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(url).toBe(`/api/bff/accounting/ledgers/${L}/entries/cost-transfer`);
    expect(JSON.parse(String(init?.body))).toMatchObject({ from_account_id: "a1", to_account_id: "a2", amount: "120.00" });
  });
});

describe("EntryActions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("blocks posting an unchecked opening balance", () => {
    renderIntl(
      <EntryActions ledgerId={L} entry={{ id: "e1", status: "draft", kind: "opening_balance", approved_by: null }} canCreate canApprove />,
    );
    expect(screen.getByText("Buchen")).toBeDisabled();
    expect(screen.getByText("Anfangsbestand prüfen")).toBeInTheDocument();
  });

  it("reverses a posted entry with a reason", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ id: "r1" }, 201));
    renderIntl(<EntryActions ledgerId={L} entry={{ id: "e1", status: "posted", kind: "custom" }} canCreate canApprove={false} />);
    expect(screen.queryByText("Buchen")).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("Stornieren"));
    await userEvent.type(screen.getByLabelText("Grund der Stornierung"), "Falsches Konto");
    await userEvent.click(screen.getByText("Storno buchen"));
    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(url).toBe(`/api/bff/accounting/ledgers/${L}/entries/e1/reverse`);
    expect(JSON.parse(String(init?.body))).toEqual({ reason: "Falsches Konto" });
  });

  it("offers no reversal for a reversed entry and no actions without permission", () => {
    renderIntl(<EntryActions ledgerId={L} entry={{ id: "e1", status: "posted", kind: "custom", reversed_by_id: "x" }} canCreate canApprove />);
    expect(screen.queryByText("Stornieren")).not.toBeInTheDocument();
  });
});

describe("AccountAllocationEditor", () => {
  afterEach(() => vi.restoreAllMocks());

  it("disables saving while the total is not 100 %", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ items: [{ allocation_key_id: "k1", share_percent: "60.00000000" }], total_percent: "60" }),
    );
    renderIntl(
      <AccountAllocationEditor ledgerId={L} accountId="a1" keys={[{ id: "k1", code: "MEA", name: "Miteigentumsanteile" }]} canUpdate />,
    );
    expect(await screen.findByDisplayValue("60")).toBeInTheDocument();
    expect(screen.getByTestId("allocation-total")).toHaveTextContent("60");
    expect(screen.getByText("Verteilung speichern")).toBeDisabled();
  });
});
