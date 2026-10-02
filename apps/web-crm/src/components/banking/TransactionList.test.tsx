import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import type { Transaction } from "./bankTypes";
import { PAGE_SIZE, REOPEN_PATH, TransactionList } from "./TransactionList";

const PBA = "0192abcd-0000-7000-8000-000000000031";
const ids = (n: number) => `0192abcd-0000-7000-8000-0000000000${String(n).padStart(2, "0")}`;

const tx = (n: number, extra: Partial<Transaction> = {}): Transaction => ({
  id: ids(n),
  property_bank_account_id: PBA,
  legal_entity_id: "le1",
  bank_reference: `ref-${n}`,
  booking_date: "2026-09-28",
  value_date: null,
  amount: "250.00",
  currency: "EUR",
  counterpart_name: `Zahler ${n}`,
  purpose: "Miete",
  end_to_end_id: null,
  mandate_reference: null,
  status: "new",
  possible_duplicate_of_id: null,
  transfer_pair_id: null,
  journal_entry_id: null,
  ...extra,
});

const accounts = [
  { id: PBA, property_id: "p1", property_number: "0001", property_name: "Haus", legal_entity_id: "le1", legal_entity_name: "WEG Haus", kind: "hoa", iban_masked: "DE12****1234", bank_name: "Sparkasse", holder: "WEG" },
];

function mockApi(rows: Transaction[]) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.includes("/banking/accounts")) return jsonResponse(accounts);
    if (url.includes("/banking/transactions?")) return jsonResponse(rows);
    if (url.includes("/review") || url.includes("/ignore")) return jsonResponse(tx(1, { status: "ignored" }));
    if (url.includes("/reopen")) return jsonResponse(tx(1));
    if (url.includes("/learn")) return jsonResponse({ id: "r1", name: "Gelernt: Zahler 3" }, 201);
    return jsonResponse({}, 404);
  });
  return calls;
}

describe("TransactionList", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the first page with limit and offset and applies the direction filter on the page", async () => {
    const calls = mockApi([tx(1), tx(2, { amount: "-40.00", counterpart_name: "Stadtwerke" })]);
    renderIntl(<TransactionList canBook canUpdate />);
    await waitFor(() => expect(screen.getAllByTestId("transaction-row")).toHaveLength(2));
    const first = calls.find((c) => c.url.includes("/banking/transactions?"))!;
    expect(first.url).toContain(`limit=${PAGE_SIZE}`);
    expect(first.url).toContain("offset=0");
    await userEvent.selectOptions(screen.getByLabelText("Richtung"), "out");
    expect(screen.getAllByTestId("transaction-row")).toHaveLength(1);
    expect(screen.getByTestId("transaction-row")).toHaveTextContent("Stadtwerke");
    // Direction is client side: no further request for it.
    expect(calls.filter((c) => c.url.includes("/banking/transactions?"))).toHaveLength(1);
  });

  it("sends account, status and period filters to the API and paginates by offset", async () => {
    const calls = mockApi(Array.from({ length: PAGE_SIZE }, (_, i) => tx(i + 1)));
    renderIntl(<TransactionList canBook canUpdate />);
    await waitFor(() => expect(screen.getAllByTestId("transaction-row")).toHaveLength(PAGE_SIZE));
    await userEvent.selectOptions(screen.getByLabelText("Status"), "booked");
    await waitFor(() => expect(calls.at(-1)!.url).toContain("status=booked"));
    await userEvent.selectOptions(screen.getByLabelText("Konto"), PBA);
    await waitFor(() => expect(calls.at(-1)!.url).toContain(`bank_account_id=${PBA}`));
    await userEvent.type(screen.getByLabelText("Von"), "2026-09-01");
    await userEvent.type(screen.getByLabelText("Bis"), "2026-09-30");
    await waitFor(() => expect(calls.at(-1)!.url).toContain("start=2026-09-01"));
    expect(calls.at(-1)!.url).toContain("end=2026-09-30");
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    await waitFor(() => expect(calls.at(-1)!.url).toContain(`offset=${PAGE_SIZE}`));
    expect(screen.getByText(/Seite 2/)).toBeInTheDocument();
  });

  it("clarifies a possible duplicate only with a reason and posts the decision", async () => {
    const calls = mockApi([tx(1, { status: "needs_review", possible_duplicate_of_id: ids(9) })]);
    renderIntl(<TransactionList canBook canUpdate />);
    await userEvent.click(await screen.findByRole("button", { name: "Dublette klären" }));
    const keep = screen.getByRole("button", { name: "Als echten Umsatz behalten" });
    expect(keep).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Begründung (mindestens 3 Zeichen)"), "Zwei Auszüge");
    expect(keep).toBeEnabled();
    await userEvent.click(keep);
    await waitFor(() => expect(calls.some((c) => c.url.endsWith(`/banking/transactions/${ids(1)}/review`))).toBe(true));
    const review = calls.find((c) => c.url.endsWith("/review"))!;
    expect(JSON.parse(review.init!.body as string)).toEqual({ decision: "keep", reason: "Zwei Auszüge" });
  });

  it("ignores only with a reason of at least three characters", async () => {
    const calls = mockApi([tx(1)]);
    vi.spyOn(window, "prompt").mockReturnValue("ab");
    renderIntl(<TransactionList canBook canUpdate />);
    await userEvent.click(await screen.findByRole("button", { name: "Ignorieren" }));
    expect(calls.some((c) => c.url.endsWith("/ignore"))).toBe(false);
  });

  it("offers Regel lernen on a booked incoming transaction and reports the proposal", async () => {
    const calls = mockApi([tx(3, { status: "booked", journal_entry_id: "je1" }), tx(4, { status: "booked", amount: "-10.00", journal_entry_id: "je2" })]);
    renderIntl(<TransactionList canBook canUpdate />);
    const rows = await screen.findAllByTestId("transaction-row");
    expect(within(rows[0]!).getByRole("button", { name: "Regel lernen" })).toBeInTheDocument();
    expect(within(rows[1]!).queryByRole("button", { name: "Regel lernen" })).not.toBeInTheDocument();
    await userEvent.click(within(rows[0]!).getByRole("button", { name: "Regel lernen" }));
    await waitFor(() => expect(screen.getByTestId("list-notice")).toHaveTextContent("Gelernt: Zahler 3"));
    expect(calls.some((c) => c.url.endsWith(`/banking/transactions/${ids(3)}/learn`) && c.init?.method === "POST")).toBe(true);
  });

  it("reopens an ignored transaction with a reason", async () => {
    const calls = mockApi([tx(1, { status: "ignored" }), tx(2)]);
    vi.spyOn(window, "prompt").mockReturnValue("Fehlerhaft ignoriert");
    renderIntl(<TransactionList canBook canUpdate />);
    const rows = await screen.findAllByTestId("transaction-row");
    expect(within(rows[1]!).queryByRole("button", { name: "Wieder eröffnen" })).not.toBeInTheDocument();
    await userEvent.click(within(rows[0]!).getByRole("button", { name: "Wieder eröffnen" }));
    await waitFor(() => expect(screen.getByTestId("list-notice")).toHaveTextContent("wieder eröffnet"));
    const call = calls.find((c) => c.url.endsWith(`/banking/transactions/${ids(1)}/reopen`));
    expect(call?.init?.method).toBe("POST");
    expect(JSON.parse(String(call?.init?.body))).toEqual({ reason: "Fehlerhaft ignoriert" });
  });

  it("sends no reopen request for a too short reason", async () => {
    const calls = mockApi([tx(1, { status: "ignored" })]);
    vi.spyOn(window, "prompt").mockReturnValue("ab");
    renderIntl(<TransactionList canBook canUpdate />);
    await userEvent.click(await screen.findByRole("button", { name: "Wieder eröffnen" }));
    expect(calls.some((c) => c.url.endsWith("/reopen"))).toBe(false);
  });

  it("hides reopening and booking without permission", async () => {
    mockApi([tx(1, { status: "ignored" }), tx(2)]);
    renderIntl(<TransactionList canBook={false} canUpdate={false} />);
    const rows = await screen.findAllByTestId("transaction-row");
    expect(REOPEN_PATH?.("x")).toBe("/api/bff/banking/transactions/x/reopen");
    expect(within(rows[0]!).queryByRole("button", { name: "Wieder eröffnen" })).not.toBeInTheDocument();
    expect(within(rows[1]!).queryByRole("button", { name: "Buchen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Massenbestätigung/ })).not.toBeInTheDocument();
  });

  it("selects new transactions of the page for the bulk confirmation, never transfer pairs", async () => {
    mockApi([tx(1), tx(2, { transfer_pair_id: ids(3) }), tx(3, { amount: "-250.00", transfer_pair_id: ids(2) }), tx(4, { status: "booked" })]);
    renderIntl(<TransactionList canBook canUpdate />);
    await screen.findAllByTestId("transaction-row");
    await userEvent.click(screen.getByRole("button", { name: "Neue Umsätze der Seite auswählen" }));
    expect(screen.getByRole("button", { name: "Massenbestätigung (1)" })).toBeEnabled();
    expect(screen.getAllByText("Umbuchung")).toHaveLength(2);
  });
});
