import { act, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { JournalEntryForm, sumCents, toDecimal, type LedgerAccountOption } from "./JournalEntryForm";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const accounts: LedgerAccountOption[] = [
  { id: "a1", number: "1200", name: "Bank", category: "bank", active: true },
  { id: "a2", number: "6000", name: "Kosten", category: "cost", active: true },
  { id: "a3", number: "9999", name: "Inaktiv", category: "cost", active: false },
];

describe("JournalEntryForm helpers", () => {
  it("converts decimals without float arithmetic", () => {
    expect(toDecimal("1.234,56")).toBe("1234.56");
    expect(toDecimal("")).toBe("0");
    expect(sumCents(["0,10", "0,20"])).toBe(30);
  });
});

describe("JournalEntryForm", { timeout: 20000 }, () => {
  afterEach(() => vi.unstubAllGlobals());

  async function fillManual(debit: string, credit: string) {
    const selects = screen.getAllByRole("combobox", { name: "Konto" });
    fireEvent.change(selects[0]!, { target: { value: "a1" } });
    fireEvent.change(selects[1]!, { target: { value: "a2" } });
    const debits = screen.getAllByRole("textbox", { name: "Soll" });
    const credits = screen.getAllByRole("textbox", { name: "Haben" });
    fireEvent.change(debits[0]!, { target: { value: debit } });
    fireEvent.change(credits[1]!, { target: { value: credit } });
    fireEvent.change(screen.getByLabelText("Buchungstext"), { target: { value: "Testbuchung" } });
  }

  it("blocks an unbalanced entry", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<JournalEntryForm ledgerId="L1" accounts={accounts} today="2026-10-02" />);
    await fillManual("10,00", "5,00");
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Entwurf speichern" }));
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Soll und Haben müssen gleich");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts a balanced draft and refreshes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "e1" }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<JournalEntryForm ledgerId="L1" accounts={accounts} today="2026-10-02" />);
    expect(screen.queryByText(/9999/)).toBeNull();
    await fillManual("10,00", "10,00");
    expect(screen.getByTestId("entry-sums")).toHaveTextContent("10,00");
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Entwurf speichern" }));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/accounting/ledgers/L1/entries");
    const body = JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string);
    expect(body.booking_date).toBe("2026-10-02");
    expect(body.lines).toHaveLength(2);
    expect(body.lines[0]).toMatchObject({ account_id: "a1", debit: "10.00", credit: "0" });
    expect(await screen.findByRole("status")).toHaveTextContent("Entwurf angelegt.");
    expect(refresh).toHaveBeenCalled();
  });

  it("shows the API error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Fehler", status: 409, detail: "gesperrt" }, 409)));
    renderIntl(<JournalEntryForm ledgerId="L1" accounts={accounts} today="2026-10-02" />);
    await fillManual("10,00", "10,00");
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Entwurf speichern" }));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("switches to interest mode and shows the net amount", async () => {
    renderIntl(<JournalEntryForm ledgerId="L1" accounts={accounts} today="2026-10-02" />);
    const mode = screen.getByLabelText(/^Vorgang/);
    fireEvent.change(mode, { target: { value: "interest" } });
    fireEvent.change(screen.getByLabelText(/^Betrag in EUR/), { target: { value: "100,00" } });
    expect(screen.getByTestId("interest-net")).toHaveTextContent("100,00");
  });
});
