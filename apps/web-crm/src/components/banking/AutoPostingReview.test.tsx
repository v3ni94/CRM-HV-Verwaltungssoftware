import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AutoPostingReview, type ReviewItem } from "./AutoPostingReview";

const ITEM = "0192abcd-0000-7000-8000-000000000081";
const TX = "0192abcd-0000-7000-8000-000000000082";
const LEDGER = "0192abcd-0000-7000-8000-000000000040";
const ACC = "0192abcd-0000-7000-8000-000000000021";

const item: ReviewItem = {
  id: ITEM,
  posting_decision_id: "d1",
  bank_transaction_id: TX,
  legal_entity_id: "le1",
  journal_entry_id: "e1",
  journal_number: "2026-17",
  ledger_id: LEDGER,
  rule_id: "r1",
  case_kind: "debtor_full",
  kind: "daily",
  due_on: "2026-09-30",
  overdue: false,
  status: "open",
  note: null,
  booking_date: "2026-09-29",
  amount: "250.00",
  counterpart_name: "Eigentümer Muster",
  purpose: "Hausgeld September",
  final: { settlements: [{ open_item_id: "oi", amount: "250.00" }], counter_account_number: null },
  verifier_fingerprint: "f".repeat(64),
  reversed: false,
  return_transaction_id: null,
};

function mockApi() {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/banking/auto-posting/reviews")) {
      return jsonResponse([
        item,
        { ...item, id: "late", overdue: true, kind: "sample", due_on: "2026-09-20" },
        { ...item, id: "ret", kind: "return", return_transaction_id: "tx-ret" },
      ]);
    }
    if (url.endsWith(`/banking/auto-posting/reviews/${ITEM}`)) return jsonResponse({ ...item, status: "ok" });
    if (url.endsWith(`/accounting/ledgers/${LEDGER}/accounts`)) {
      return jsonResponse([
        { id: ACC, number: "060100", name: "Hausgeld", category: "income", type: "income", active: true, is_system: false, property_bank_account_id: null },
        { id: "bank", number: "001210", name: "Bank", category: "bank", type: "asset", active: true, is_system: false, property_bank_account_id: "pba" },
      ]);
    }
    if (url.endsWith(`/banking/transactions/${TX}/correct`)) return jsonResponse({ reversal_id: "s", reversal_number: "2026-18", journal_entry_id: "n", number: "2026-19" }, 201);
    return jsonResponse({}, 404);
  });
  return calls;
}

describe("AutoPostingReview", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists open items with due date and kind and confirms one as ok", async () => {
    const calls = mockApi();
    renderIntl(<AutoPostingReview canReview canBook />);
    const rows = await screen.findAllByTestId("review-item");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("Eigentümer Muster");
    expect(rows[0]).toHaveTextContent("250,00 EUR");
    expect(rows[0]).toHaveTextContent("Tagesprüfung");
    expect(rows[1]).toHaveTextContent("überfällig");
    expect(rows[1]).toHaveTextContent("Stichprobe");
    expect(rows[2]).toHaveTextContent("Rückläufer");
    expect(rows[2]).toHaveTextContent("Die Bank hat die Zahlung zurückgegeben");
    await userEvent.click(within(rows[0]!).getByRole("button", { name: "In Ordnung" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith(`/banking/auto-posting/reviews/${ITEM}`) && c.init?.method === "POST")).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.url.endsWith(`/reviews/${ITEM}`))?.init?.body))).toEqual({ outcome: "ok" });
    expect(await screen.findByText("Buchung 2026-17 bestätigt.")).toBeInTheDocument();
  });

  it("corrects with reason code, counter account and reason in one call (Storno plus Neubuchung)", async () => {
    const calls = mockApi();
    renderIntl(<AutoPostingReview canReview canBook />);
    const rows = await screen.findAllByTestId("review-item");
    await userEvent.click(within(rows[0]!).getByRole("button", { name: "Korrigieren" }));
    const form = await screen.findByTestId("correct-form");
    const submit = within(form).getByRole("button", { name: "Stornieren und neu buchen" });
    expect(submit).toBeDisabled();
    await waitFor(() => expect(within(form).getByRole("option", { name: "060100 Hausgeld" })).toBeInTheDocument());
    expect(within(form).queryByRole("option", { name: "001210 Bank" })).not.toBeInTheDocument();
    await userEvent.selectOptions(within(form).getByLabelText("Gegenkonto der Neubuchung"), ACC);
    await userEvent.selectOptions(within(form).getByLabelText("Grundcode"), "wrong_assignment");
    await userEvent.type(within(form).getByLabelText("Begründung"), "Falscher Posten getroffen");
    await userEvent.click(submit);
    await waitFor(() => expect(calls.some((c) => c.url.endsWith(`/banking/transactions/${TX}/correct`))).toBe(true));
    const sent = JSON.parse(String(calls.find((c) => c.url.endsWith("/correct"))?.init?.body));
    expect(sent).toEqual({ reason: "Falscher Posten getroffen", reason_code: "wrong_assignment", settlements: [], counter_account_id: ACC });
    expect(await screen.findByText("Storno 2026-18 gebucht, Neubuchung 2026-19.")).toBeInTheDocument();
  });

  it("hides In Ordnung without accounting:review and Korrigieren without accounting:create", async () => {
    mockApi();
    renderIntl(<AutoPostingReview canReview={false} canBook={false} />);
    await screen.findAllByTestId("review-item");
    expect(screen.queryByRole("button", { name: "In Ordnung" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Korrigieren" })).not.toBeInTheDocument();
  });
});
