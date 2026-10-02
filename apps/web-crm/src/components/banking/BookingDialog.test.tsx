import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import type { Transaction } from "./bankTypes";
import { API_SUPPORTS_DISCOUNT, BookingDialog, STAGE1_REJECT_PATH } from "./BookingDialog";

const TX = "0192abcd-0000-7000-8000-000000000002";
const LEDGER = "0192abcd-0000-7000-8000-000000000004";
const OI1 = "0192abcd-0000-7000-8000-000000000011";
const OI2 = "0192abcd-0000-7000-8000-000000000012";
const ACC_DEBTOR = "0192abcd-0000-7000-8000-000000000021";
const ACC_COST = "0192abcd-0000-7000-8000-000000000022";
const ACC_BANK_OWN = "0192abcd-0000-7000-8000-000000000023";
const ACC_BANK_OTHER = "0192abcd-0000-7000-8000-000000000024";
const ACC_SYSTEM = "0192abcd-0000-7000-8000-000000000025";
const ACC_INACTIVE = "0192abcd-0000-7000-8000-000000000026";
const OWN_PBA = "0192abcd-0000-7000-8000-000000000031";
const OTHER_PBA = "0192abcd-0000-7000-8000-000000000032";
const AI_ID = "0192abcd-0000-7000-8000-000000000041";

const tx = (extra: Partial<Transaction> = {}): Transaction => ({
  id: TX,
  property_bank_account_id: OWN_PBA,
  legal_entity_id: "le1",
  bank_reference: "ref",
  booking_date: "2026-09-28",
  value_date: null,
  amount: "250.00",
  currency: "EUR",
  counterpart_name: "Mieter Muster",
  purpose: "Miete 09/2026",
  end_to_end_id: null,
  mandate_reference: null,
  status: "new",
  possible_duplicate_of_id: null,
  transfer_pair_id: null,
  journal_entry_id: null,
  ...extra,
});

const accounts = [
  { id: ACC_DEBTOR, number: "1400", name: "Debitor Muster", category: "debtor", type: "asset", active: true, is_system: false, property_bank_account_id: null },
  { id: ACC_COST, number: "4200", name: "Instandhaltung", category: "cost", type: "expense", active: true, is_system: false, property_bank_account_id: null },
  { id: ACC_BANK_OWN, number: "1200", name: "Bank Miete", category: "bank", type: "asset", active: true, is_system: false, property_bank_account_id: OWN_PBA },
  { id: ACC_BANK_OTHER, number: "1210", name: "Bank Rücklage", category: "bank", type: "asset", active: true, is_system: false, property_bank_account_id: OTHER_PBA },
  { id: ACC_SYSTEM, number: "9000", name: "Saldenvortrag", category: "technical", type: "asset", active: true, is_system: true, property_bank_account_id: null },
  { id: ACC_INACTIVE, number: "4300", name: "Alt", category: "cost", type: "expense", active: false, is_system: false, property_bank_account_id: null },
];
const openItems = [
  { id: OI1, account_id: ACC_DEBTOR, account_number: "1400", kind: "rent", journal_entry_id: null, booking_date: "2026-09-01", due_date: "2026-09-03", amount: "250.00", remaining: "250.00", contract_id: null },
  { id: OI2, account_id: ACC_DEBTOR, account_number: "1400", kind: "rent", journal_entry_id: null, booking_date: "2026-08-01", due_date: "2026-08-03", amount: "250.00", remaining: "100.00", contract_id: null },
];

function proposals(extra: Partial<{ stage1: unknown[]; ai: unknown[] }> = {}) {
  return {
    ledger_id: LEDGER,
    stage1: extra.stage1 ?? [
      {
        source: "match",
        kind: "full",
        confidence: 0.85,
        reasoning: ["Vertragsnummer im Verwendungszweck"],
        account_number: "1400",
        splits: [{ open_item_id: OI1, amount: "250.00" }],
        unambiguous: true,
      },
    ],
    ai: extra.ai ?? [],
    ai_stage: { enabled: false, blocked_reason: "Mandantenschalter aus." },
    note: "Vorschläge, keine Buchung.",
  };
}

function mockApi(overrides: Partial<Record<string, () => Response>> = {}) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    const custom = Object.entries(overrides).find(([key]) => url.includes(key));
    if (custom) return custom[1]!();
    if (url.includes("/posting-proposals")) return jsonResponse(proposals());
    if (url.includes("/accounts")) return jsonResponse(accounts);
    if (url.includes("/open-items")) return jsonResponse(openItems);
    if (url.includes("/book")) return jsonResponse({ journal_entry_id: "je1", number: "2026-7" }, 201);
    if (url.includes("/reject")) return jsonResponse({ id: AI_ID, decision: "rejected" });
    return jsonResponse({}, 404);
  });
  return calls;
}

describe("BookingDialog", () => {
  afterEach(() => vi.restoreAllMocks());

  it("offers only cost and personal accounts as contra account, never bank, system or inactive ones", async () => {
    mockApi();
    renderIntl(<BookingDialog tx={tx()} onClose={() => {}} onBooked={() => {}} />);
    const list = await screen.findByTestId("contra-candidates");
    await waitFor(() => expect(within(list).getAllByRole("button").length).toBeGreaterThan(0));
    const labels = within(list).getAllByRole("button").map((b) => b.textContent);
    expect(labels).toEqual(["1400 Debitor Muster", "4200 Instandhaltung"]);
  });

  it("books a free choice of open items with a partial amount and a contra account for the rest", async () => {
    const calls = mockApi();
    const onBooked = vi.fn();
    renderIntl(<BookingDialog tx={tx()} onClose={() => {}} onBooked={onBooked} />);
    const candidates = await screen.findByTestId("open-item-candidates");
    await waitFor(() => expect(within(candidates).getAllByText("Hinzufügen").length).toBe(2));
    // Second item (remaining 100,00) first: allocation 100,00, rest 150,00.
    await userEvent.click(within(candidates).getAllByText("Hinzufügen")[1]!);
    expect(screen.getByTestId("allocated")).toHaveTextContent("100,00 EUR");
    expect(screen.getByTestId("rest")).toHaveTextContent("150,00 EUR");
    // Partial amount on the first item: 120,00 instead of the remaining 250,00.
    await userEvent.click(within(candidates).getAllByText("Hinzufügen")[0]!);
    const amountInput = screen.getByLabelText("Betrag für 1400 Debitor Muster, fällig 03.09.2026", { selector: "input" });
    await userEvent.clear(amountInput);
    await userEvent.type(amountInput, "120,00");
    expect(screen.getByTestId("rest")).toHaveTextContent("30,00 EUR");
    // Same debtor account for both items: the remainder may stay as credit (D07), so booking
    // is possible; with a contra account the remainder goes there instead.
    expect(screen.getByText(/Guthaben auf dem Personenkonto/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "4200 Instandhaltung" }));
    expect(screen.getByTestId("contra-selected")).toHaveTextContent("4200 Instandhaltung");
    await userEvent.click(screen.getByRole("button", { name: "Buchen" }));
    expect(screen.getByTestId("confirm-box")).toHaveTextContent("250,00 EUR");
    await userEvent.click(screen.getByRole("button", { name: "Buchung bestätigen" }));
    await waitFor(() => expect(onBooked).toHaveBeenCalledWith({ journal_entry_id: "je1", number: "2026-7" }));
    const book = calls.find((c) => c.url.endsWith(`/banking/transactions/${TX}/book`));
    expect(JSON.parse(book!.init!.body as string)).toEqual({
      settlements: [
        { open_item_id: OI2, amount: "100.00" },
        { open_item_id: OI1, amount: "120.00" },
      ],
      counter_account_id: ACC_COST,
    });
  });

  it("reads a partial amount in the displayed notation and names an unreadable one", async () => {
    mockApi();
    renderIntl(<BookingDialog tx={tx({ amount: "1250.00" })} onClose={() => {}} onBooked={() => {}} />);
    const candidates = await screen.findByTestId("open-item-candidates");
    await waitFor(() => expect(within(candidates).getAllByText("Hinzufügen").length).toBe(2));
    await userEvent.click(within(candidates).getAllByText("Hinzufügen")[0]!);
    const amountInput = screen.getByLabelText("Betrag für 1400 Debitor Muster, fällig 03.09.2026", { selector: "input" });
    // The displayed notation with a thousands separator is an amount, not 0,00.
    await userEvent.clear(amountInput);
    await userEvent.type(amountInput, "1.250,00");
    expect(screen.getByTestId("allocated")).toHaveTextContent("1.250,00 EUR");
    expect(screen.getByTestId("rest")).toHaveTextContent("0,00 EUR");
    expect(screen.queryByText(/nicht lesbar/)).not.toBeInTheDocument();
    expect(screen.queryByText(/größer als 0,00 EUR/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Buchen" })).toBeEnabled();
    // Two dots cannot be read: own message, no misleading "greater than 0,00", booking locked.
    await userEvent.clear(amountInput);
    await userEvent.type(amountInput, "1.250.00");
    expect(screen.getByText(/Betrag nicht lesbar/)).toBeInTheDocument();
    expect(screen.queryByText(/größer als 0,00 EUR/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Buchen" })).toBeDisabled();
    // A readable 0,00 keeps the existing message.
    await userEvent.clear(amountInput);
    await userEvent.type(amountInput, "0,00");
    expect(screen.getByText(/größer als 0,00 EUR/)).toBeInTheDocument();
    expect(screen.queryByText(/nicht lesbar/)).not.toBeInTheDocument();
  });

  it("refuses an allocation above the payment amount and a remainder without contra account", async () => {
    mockApi();
    renderIntl(<BookingDialog tx={tx({ amount: "50.00" })} onClose={() => {}} onBooked={() => {}} />);
    const candidates = await screen.findByTestId("open-item-candidates");
    await waitFor(() => expect(within(candidates).getAllByText("Hinzufügen").length).toBe(2));
    // Nothing allocated: the whole amount is a remainder without target.
    expect(screen.getByRole("button", { name: "Buchen" })).toBeDisabled();
    expect(screen.getByText(/Restbetrag braucht ein Gegenkonto/)).toBeInTheDocument();
    await userEvent.click(within(candidates).getAllByText("Hinzufügen")[0]!);
    // Suggested amount is capped at the remainder (50,00), not the item's 250,00.
    expect(screen.getByTestId("allocated")).toHaveTextContent("50,00 EUR");
    const amountInput = screen.getByLabelText("Betrag für 1400 Debitor Muster, fällig 03.09.2026", { selector: "input" });
    await userEvent.clear(amountInput);
    await userEvent.type(amountInput, "80");
    expect(screen.getByText("Zuordnung höher als der Zahlbetrag.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Buchen" })).toBeDisabled();
  });

  it("takes over a proposal on click and shows source, confidence and reasoning", async () => {
    mockApi();
    renderIntl(<BookingDialog tx={tx()} onClose={() => {}} onBooked={() => {}} />);
    const row = await screen.findByTestId("proposal-row");
    expect(row).toHaveTextContent("Abgleich");
    expect(row).toHaveTextContent("Konfidenz 85 %");
    expect(row).toHaveTextContent("Vertragsnummer im Verwendungszweck");
    expect(screen.getByTestId("allocated")).toHaveTextContent("0,00 EUR");
    await userEvent.click(within(row).getByText("Übernehmen"));
    expect(screen.getByTestId("allocated")).toHaveTextContent("250,00 EUR");
    expect(screen.getByTestId("rest")).toHaveTextContent("0,00 EUR");
  });

  it("books an outgoing payment against a contra account", async () => {
    const calls = mockApi({ "/posting-proposals": () => jsonResponse(proposals({ stage1: [] })) });
    const onBooked = vi.fn();
    renderIntl(<BookingDialog tx={tx({ amount: "-89.90", counterpart_name: "Stadtwerke" })} onClose={() => {}} onBooked={onBooked} />);
    expect(await screen.findByText("Ausgang")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "4200 Instandhaltung" }));
    await userEvent.type(screen.getByLabelText("Buchungstext"), "Abschlag Strom");
    await userEvent.click(screen.getByRole("button", { name: "Buchen" }));
    await userEvent.click(screen.getByRole("button", { name: "Buchung bestätigen" }));
    await waitFor(() => expect(onBooked).toHaveBeenCalled());
    const book = calls.find((c) => c.url.endsWith("/book"));
    expect(JSON.parse(book!.init!.body as string)).toEqual({ settlements: [], counter_account_id: ACC_COST, text: "Abschlag Strom" });
  });

  it("books a transfer pair against the preselected partner bank account without settlements", async () => {
    const calls = mockApi({ "/posting-proposals": () => jsonResponse(proposals({ stage1: [] })) });
    const onBooked = vi.fn();
    renderIntl(
      <BookingDialog tx={tx({ amount: "-1000.00", transfer_pair_id: "0192abcd-0000-7000-8000-000000000099" })} partnerBankAccountId={OTHER_PBA} onClose={() => {}} onBooked={onBooked} />,
    );
    await waitFor(() => expect(screen.getByTestId("contra-selected")).toHaveTextContent("1210 Bank Rücklage"));
    expect(screen.queryByTestId("open-item-candidates")).not.toBeInTheDocument();
    const list = screen.getByTestId("contra-candidates");
    expect(within(list).queryByRole("button", { name: "1200 Bank Miete" })).not.toBeInTheDocument();
    expect(within(list).queryByRole("button", { name: "4200 Instandhaltung" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Buchen" }));
    await userEvent.click(screen.getByRole("button", { name: "Buchung bestätigen" }));
    await waitFor(() => expect(onBooked).toHaveBeenCalled());
    const book = calls.find((c) => c.url.endsWith("/book"));
    expect(JSON.parse(book!.init!.body as string)).toEqual({ settlements: [], counter_account_id: ACC_BANK_OTHER });
  });

  it("rejects an AI proposal only with a reason of at least three characters", async () => {
    const calls = mockApi({
      "/posting-proposals": () =>
        jsonResponse(
          proposals({
            stage1: [],
            ai: [{ id: AI_ID, decision: "pending", source: "ai", kind: "posting", confidence: 0.4, reasoning: "Betrag passt", account_number: "1400", proposed: { splits: [] } }],
          }),
        ),
    });
    renderIntl(<BookingDialog tx={tx()} onClose={() => {}} onBooked={() => {}} />);
    const row = await screen.findByTestId("proposal-row");
    expect(row).toHaveTextContent("KI");
    await userEvent.click(within(row).getByText("Ablehnen"));
    const reason = within(row).getByLabelText("Grund der Ablehnung (mindestens 3 Zeichen)");
    await userEvent.type(reason, "ab");
    expect(within(row).getByRole("button", { name: "Ablehnung speichern" })).toBeDisabled();
    await userEvent.type(reason, "c");
    await userEvent.click(within(row).getByRole("button", { name: "Ablehnung speichern" }));
    await waitFor(() => expect(screen.getByText("abgelehnt")).toBeInTheDocument());
    const reject = calls.find((c) => c.url.endsWith(`/ai/proposals/${AI_ID}/reject`));
    expect(JSON.parse(reject!.init!.body as string)).toEqual({ reason: "abc" });
  });

  it("keeps discount and stage 1 rejection as marked hooks until the API offers them", async () => {
    mockApi();
    renderIntl(<BookingDialog tx={tx()} onClose={() => {}} onBooked={() => {}} />);
    expect(API_SUPPORTS_DISCOUNT).toBe(false);
    expect(STAGE1_REJECT_PATH).toBeNull();
    expect(screen.getByRole("textbox", { name: "Skonto" })).toBeDisabled();
    const row = await screen.findByTestId("proposal-row");
    expect(within(row).queryByText("Ablehnen")).not.toBeInTheDocument();
    expect(screen.getByText(/Entscheidungsprotokoll \(Schritt S1\)/)).toBeInTheDocument();
  });

  it("shows the object period lock and disables booking (GAH-401)", async () => {
    mockApi({
      "/posting-proposals": () =>
        jsonResponse({ ...proposals(), object_period_lock: { locked: true, code: "MHVP-ACC-0030" } }),
    });
    renderIntl(<BookingDialog tx={tx()} onClose={() => {}} onBooked={() => {}} />);
    const hint = await screen.findByTestId("period-lock-hint");
    expect(hint).toHaveTextContent("MHVP-ACC-0030");
    const candidates = await screen.findByTestId("open-item-candidates");
    await waitFor(() => expect(within(candidates).getAllByText("Hinzufügen").length).toBe(2));
    await userEvent.click(within(candidates).getAllByText("Hinzufügen")[0]!);
    expect(screen.getByRole("button", { name: "Buchen" })).toBeDisabled();
  });
});
