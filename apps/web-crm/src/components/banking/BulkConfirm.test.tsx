import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import type { Proposals, Transaction } from "./bankTypes";
import { BulkConfirm, verifiedSplits } from "./BulkConfirm";

const ids = (n: number) => `0192abcd-0000-7000-8000-0000000000${String(n).padStart(2, "0")}`;
const OI = ids(50);

const tx = (n: number, extra: Partial<Transaction> = {}): Transaction => ({
  id: ids(n),
  property_bank_account_id: ids(30),
  legal_entity_id: n % 2 === 0 ? "le2" : "le1",
  bank_reference: `ref-${n}`,
  booking_date: "2026-09-28",
  value_date: null,
  amount: "100.00",
  currency: "EUR",
  counterpart_name: `Zahler ${n}`,
  purpose: "Hausgeld",
  end_to_end_id: null,
  mandate_reference: null,
  status: "new",
  possible_duplicate_of_id: null,
  transfer_pair_id: null,
  journal_entry_id: null,
  ...extra,
});

const base = (stage1: Proposals["stage1"], ai: Proposals["ai"] = []): Proposals => ({
  ledger_id: ids(40),
  stage1,
  ai,
  ai_stage: { enabled: false, blocked_reason: "aus" },
  note: "",
});
const split = (amount = "100.00") => [{ open_item_id: OI, amount }];

describe("verifiedSplits", () => {
  it("accepts only an unambiguous match or a rule hit, never history, weak or AI proposals", () => {
    expect(verifiedSplits(base([{ source: "match", kind: "full", confidence: 0.9, reasoning: null, account_number: "1400", splits: split(), unambiguous: true }]))).toEqual(split());
    expect(verifiedSplits(base([{ source: "rule", kind: "debtor_payment", confidence: 0.9, reasoning: null, account_number: "1400", splits: split() }]))).toEqual(split());
    expect(verifiedSplits(base([{ source: "match", kind: "weak", confidence: 0.3, reasoning: null, account_number: "1400", splits: split(), unambiguous: false }]))).toBeNull();
    expect(verifiedSplits(base([{ source: "match", kind: "partial", confidence: 0.6, reasoning: null, account_number: "1400", splits: split("40.00") }]))).toBeNull();
    expect(
      verifiedSplits(base([], [{ id: ids(60), decision: "pending", source: "ai", kind: "posting", confidence: 0.99, reasoning: null, account_number: "1400", proposed: { splits: split() } }])),
    ).toBeNull();
  });
});

describe("BulkConfirm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("previews only the bookable items (API exceptions excluded), then books exactly those", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url.includes(`${ids(1)}/posting-proposals`) || url.includes(`${ids(2)}/posting-proposals`)) {
        return jsonResponse(base([{ source: "match", kind: "full", confidence: 0.9, reasoning: null, account_number: "1400", splits: split(), unambiguous: true }]));
      }
      if (url.includes("/posting-proposals")) return jsonResponse(base([]));
      if (url.endsWith("/banking/bulk-confirm")) {
        const body = JSON.parse(init!.body as string);
        if (body.preview) {
          return jsonResponse({ preview: true, count: 2, total: "200.00", legal_entities: ["le1", "le2"], exceptions: [ids(2)], preview_id: "1999999999.abc", allocations: {} });
        }
        return jsonResponse({
          preview: false,
          count: 2,
          total: "200.00",
          legal_entities: ["le1", "le2"],
          exceptions: [],
          results: [
            { transaction_id: ids(1), ok: true, journal_entry_id: "je1" },
            { transaction_id: ids(2), ok: false, error: "Der Umsatz ist bereits gebucht oder ignoriert." },
          ],
        });
      }
      return jsonResponse({}, 404);
    });
    const onDone = vi.fn();
    const names = new Map([
      ["le1", "WEG Nord"],
      ["le2", "WEG Süd"],
    ]);
    renderIntl(<BulkConfirm transactions={[tx(1), tx(2), tx(3)]} legalEntityNames={names} onClose={() => {}} onDone={onDone} />);
    // The API counts and sums all submitted items (count 2, total 200,00) and lists tx 2 as
    // an exception; the dialog shows only what will be booked: tx 1 of WEG Nord, 100,00.
    await waitFor(() => expect(screen.getByTestId("bulk-count")).toHaveTextContent("1"));
    expect(screen.getByTestId("bulk-total")).toHaveTextContent("100,00 EUR");
    expect(screen.getByText("WEG Nord")).toBeInTheDocument();
    expect(screen.queryByText("WEG Süd")).not.toBeInTheDocument();
    const exceptions = screen.getByTestId("bulk-exceptions");
    expect(exceptions).toHaveTextContent("Zahler 3");
    expect(exceptions).toHaveTextContent("kein geprüfter Vorschlag");
    expect(exceptions).toHaveTextContent("Zahler 2");
    const preview = calls.find((c) => c.url.endsWith("/banking/bulk-confirm"))!;
    const previewBody = JSON.parse(preview.init!.body as string);
    expect(previewBody.preview).toBe(true);
    expect(previewBody.items).toHaveLength(2);
    expect(previewBody.items[0]).toEqual({ transaction_id: ids(1), settlements: split() });
    expect(screen.queryByRole("button", { name: "2 Umsätze buchen" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "1 Umsatz buchen" }));
    // The API result is rendered as returned (a state change between preview and confirmation
    // may still fail an item); the confirmation itself carries only the bookable item.
    await waitFor(() => expect(screen.getByTestId("bulk-result")).toHaveTextContent("1 gebucht, 1 nicht gebucht."));
    expect(screen.getByText(/bereits gebucht oder ignoriert/)).toBeInTheDocument();
    const confirm = calls.filter((c) => c.url.endsWith("/banking/bulk-confirm")).at(-1)!;
    const confirmBody = JSON.parse(confirm.init!.body as string);
    expect(confirmBody.preview).toBe(false);
    // GAK-105: the booking call carries the token of the preview.
    expect(confirmBody.preview_id).toBe("1999999999.abc");
    expect(confirmBody.items).toEqual([{ transaction_id: ids(1), settlements: split() }]);
    await userEvent.click(screen.getByRole("button", { name: "Schließen" }));
    expect(onDone).toHaveBeenCalled();
  });

  it("disables the confirmation when every verified item is an API exception", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url.includes("/posting-proposals")) {
        return jsonResponse(base([{ source: "match", kind: "full", confidence: 0.9, reasoning: null, account_number: "1400", splits: split(), unambiguous: true }]));
      }
      if (url.endsWith("/banking/bulk-confirm")) {
        return jsonResponse({ preview: true, count: 1, total: "100.00", legal_entities: ["le1"], exceptions: [ids(1)], allocations: {} });
      }
      return jsonResponse({}, 404);
    });
    renderIntl(<BulkConfirm transactions={[tx(1)]} legalEntityNames={new Map([["le1", "WEG Nord"]])} onClose={() => {}} onDone={() => {}} />);
    await waitFor(() => expect(screen.getByTestId("bulk-exceptions")).toHaveTextContent("Zahler 1"));
    expect(screen.getByTestId("bulk-count")).toHaveTextContent("0");
    expect(screen.getByTestId("bulk-total")).toHaveTextContent("0,00 EUR");
    expect(screen.queryByText("WEG Nord")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "0 Umsätze buchen" })).toBeDisabled();
    expect(calls.filter((c) => c.url.endsWith("/banking/bulk-confirm"))).toHaveLength(1);
  });

  it("books nothing when no selected transaction has a verified proposal", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      calls.push(String(input));
      return jsonResponse(base([{ source: "match", kind: "weak", confidence: 0.3, reasoning: null, account_number: "1400", splits: split(), unambiguous: false }]));
    });
    renderIntl(<BulkConfirm transactions={[tx(1)]} legalEntityNames={new Map()} onClose={() => {}} onDone={() => {}} />);
    await waitFor(() => expect(screen.getByTestId("bulk-count")).toHaveTextContent("0"));
    expect(screen.getByRole("button", { name: "0 Umsätze buchen" })).toBeDisabled();
    expect(calls.some((url) => url.endsWith("/banking/bulk-confirm"))).toBe(false);
  });

  it("lists transactions with a locked object period as exceptions and never submits them (GAH-401)", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      const full = { source: "match" as const, kind: "full", confidence: 0.9, reasoning: null, account_number: "1400", splits: split(), unambiguous: true };
      if (url.includes(`${ids(1)}/posting-proposals`)) return jsonResponse({ ...base([full]), object_period_lock: { locked: true, code: "MHVP-ACC-0030" } });
      if (url.includes("/posting-proposals")) return jsonResponse(base([full]));
      if (url.endsWith("/banking/bulk-confirm")) {
        return jsonResponse({ preview: true, count: 1, total: "100.00", legal_entities: ["le2"], exceptions: [], allocations: {} });
      }
      return jsonResponse({}, 404);
    });
    renderIntl(<BulkConfirm transactions={[tx(1), tx(2)]} legalEntityNames={new Map()} onClose={() => {}} onDone={() => {}} />);
    await waitFor(() => expect(screen.getByTestId("bulk-count")).toHaveTextContent("1"));
    expect(screen.getByTestId("bulk-period-locked")).toHaveTextContent("Zahler 1");
    expect(screen.getByTestId("bulk-period-locked")).toHaveTextContent("MHVP-ACC-0030");
    const preview = calls.find((c) => c.url.endsWith("/banking/bulk-confirm"))!;
    expect(JSON.parse(preview.init!.body as string).items).toEqual([{ transaction_id: ids(2), settlements: split() }]);
  });
});
