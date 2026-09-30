/** Auswertungsansichten der Auswertungsseite (7.7, M18-01 bis M18-09): je Ansicht der
 *  API-Pfad, die benötigten Parameter und die Abbildung der Antwort auf eine Tabelle. Reine
 *  Funktionen ohne React, damit sie einzeln testbar sind. Beträge bleiben Dezimalzeichenketten. */

export type ReportHeader = {
  report: string;
  legal_entity_name: string | null;
  ledger_name: string;
  period_start: string | null;
  period_end: string | null;
  as_of: string | null;
  generated_at: string;
  filters: Record<string, string | boolean>;
  status: string;
  status_note: string;
};

export type ViewId =
  | "accountSheet"
  | "trialBalance"
  | "openItems"
  | "monthlyMatrix"
  | "targetActual"
  | "bankStatement"
  | "vatOverview"
  | "incomeExpense";

export type Column = { key: string; label: string; kind?: "money" | "date" | "text" };
export type Table = {
  columns: Column[];
  rows: Record<string, string>[];
  summary: { label: string; value: string; kind?: "money" | "date" | "text" }[];
  notes: string[];
};

type Needs = { asOf?: boolean; period?: boolean; account?: boolean };

export const VIEWS: Record<ViewId, { path: string; needs: Needs; xlsx?: string }> = {
  accountSheet: { path: "account-sheet", needs: { period: true, account: true } },
  trialBalance: { path: "trial-balance", needs: { asOf: true }, xlsx: "trial_balance" },
  openItems: { path: "open-items", needs: { asOf: true }, xlsx: "open_items" },
  monthlyMatrix: { path: "monthly-matrix", needs: { period: true }, xlsx: "monthly_matrix" },
  targetActual: { path: "target-actual", needs: { period: true }, xlsx: "target_actual" },
  bankStatement: { path: "bank-statement", needs: { period: true, account: true } },
  vatOverview: { path: "vat-overview", needs: { period: true }, xlsx: "vat_overview" },
  incomeExpense: { path: "income-expense", needs: { period: true }, xlsx: "income_expense" },
};

type Json = Record<string, unknown>;
const str = (v: unknown): string => (v === null || v === undefined ? "" : String(v));
const list = (v: unknown): Json[] => (Array.isArray(v) ? (v as Json[]) : []);
const text = (key: string, label: string): Column => ({ key, label, kind: "text" });
const money = (key: string, label: string): Column => ({ key, label, kind: "money" });
const day = (key: string, label: string): Column => ({ key, label, kind: "date" });

/** `l` liefert die Spaltenüberschrift je Schlüssel (Übersetzung). */
export function toTable(view: ViewId, data: Json, l: (key: string) => string): Table {
  const notes: string[] = [];
  if (typeof data.note === "string") notes.push(data.note);
  if (typeof data.sign_note === "string") notes.push(data.sign_note);
  const rows = (items: Json[], keys: string[]) =>
    items.map((r) => Object.fromEntries(keys.map((k) => [k, str(r[k])])));
  switch (view) {
    case "accountSheet":
      return {
        columns: [day("booking_date", l("date")), text("number", l("number")), text("text", l("text")), money("debit", l("debit")), money("credit", l("credit")), money("balance", l("balance"))],
        rows: rows(list(data.movements), ["booking_date", "number", "text", "debit", "credit", "balance"]),
        summary: [
          { label: l("opening"), value: str(data.opening_balance), kind: "money" },
          { label: l("closing"), value: str(data.closing_balance), kind: "money" },
        ],
        notes,
      };
    case "trialBalance":
      return {
        columns: [text("number", l("account")), text("name", l("name")), money("debit", l("debit")), money("credit", l("credit")), money("balance", l("balance"))],
        rows: rows(list(data.accounts), ["number", "name", "debit", "credit", "balance"]),
        summary: [
          { label: l("debit"), value: str(data.debit), kind: "money" },
          { label: l("credit"), value: str(data.credit), kind: "money" },
        ],
        notes: data.balanced === false ? [...notes, l("unbalanced")] : notes,
      };
    case "openItems":
      return {
        columns: [text("account_number", l("account")), text("kind", l("kind")), day("booking_date", l("date")), day("due_date", l("due")), money("amount", l("amount")), money("remaining", l("remaining"))],
        rows: rows(list(data.rows), ["account_number", "kind", "booking_date", "due_date", "amount", "remaining"]),
        summary: [],
        notes,
      };
    case "monthlyMatrix": {
      const months = (Array.isArray(data.months) ? data.months : []) as string[];
      const accounts = list(data.accounts);
      return {
        columns: [text("number", l("account")), text("name", l("name")), ...months.map((m) => money(m, m)), money("total", l("total"))],
        rows: accounts.map((a) => ({
          number: str(a.number),
          name: str(a.name),
          ...Object.fromEntries(months.map((m) => [m, str((a.months as Json)?.[m])])),
          total: str(a.total),
        })),
        summary: [],
        notes,
      };
    }
    case "targetActual":
      return {
        columns: [text("number", l("account")), text("name", l("name")), money("target", l("target")), money("actual_on_target", l("actual")), money("difference", l("difference")), money("receipts_in_period", l("receipts"))],
        rows: rows(list(data.rows), ["number", "name", "target", "actual_on_target", "difference", "receipts_in_period"]),
        summary: [
          { label: l("target"), value: str(data.total_target), kind: "money" },
          { label: l("actual"), value: str(data.total_actual_on_target), kind: "money" },
          { label: l("difference"), value: str(data.total_difference), kind: "money" },
        ],
        notes,
      };
    case "bankStatement": {
      const rec = data.reconciliation as Json | null;
      const summary: Table["summary"] = [
        { label: l("opening"), value: str(data.opening_balance), kind: "money" },
        { label: l("closing"), value: str(data.closing_balance), kind: "money" },
      ];
      if (rec) {
        summary.push(
          { label: l("bankBalance"), value: str(rec.bank_closing_balance), kind: "money" },
          { label: l("bankDifference"), value: str(rec.difference), kind: "money" },
        );
      } else {
        notes.push(l("noStatement"));
      }
      return {
        columns: [day("booking_date", l("date")), text("number", l("number")), text("text", l("text")), money("debit", l("debit")), money("credit", l("credit")), money("balance", l("balance"))],
        rows: rows(list(data.movements), ["booking_date", "number", "text", "debit", "credit", "balance"]),
        summary,
        notes,
      };
    }
    case "vatOverview": {
      const byMonth = (data.by_month ?? {}) as Record<string, Json>;
      return {
        columns: [text("month", l("month")), money("output_vat", l("outputVat")), money("input_vat_before_deduction", l("inputVat"))],
        rows: Object.keys(byMonth)
          .sort()
          .map((m) => ({ month: m, output_vat: str(byMonth[m]?.output_vat), input_vat_before_deduction: str(byMonth[m]?.input_vat_before_deduction) })),
        summary: [
          { label: l("outputVat"), value: str(data.total_output_vat), kind: "money" },
          { label: l("inputVat"), value: str(data.total_input_vat_before_deduction), kind: "money" },
        ],
        notes: [
          ...notes,
          ...list(data.checkpoints).map((c) => `${str(c.id)}: ${str(c.topic)} (${str(c.status)}, ${str(c.owner)})`),
        ],
      };
    }
    case "incomeExpense":
      return {
        columns: [text("kind", l("kind")), text("number", l("account")), text("name", l("name")), money("total", l("amount"))],
        rows: [
          ...list(data.revenue).map((r) => ({ kind: l("income"), number: str(r.number), name: str(r.name), total: str(r.total) })),
          ...list(data.cost).map((r) => ({ kind: l("expense"), number: str(r.number), name: str(r.name), total: str(r.total) })),
        ],
        summary: [
          { label: l("income"), value: str(data.total_revenue), kind: "money" },
          { label: l("expense"), value: str(data.total_cost), kind: "money" },
          { label: l("surplus"), value: str(data.surplus), kind: "money" },
        ],
        notes,
      };
  }
}

export function buildQuery(
  view: ViewId,
  p: { asOf: string; start: string; end: string; accountId: string },
): string {
  const needs = VIEWS[view].needs;
  const q = new URLSearchParams();
  if (needs.asOf) q.set("as_of", p.asOf);
  if (needs.period) {
    q.set("start", p.start);
    q.set("end", p.end);
  }
  if (needs.account && p.accountId) q.set("account_id", p.accountId);
  return q.toString();
}
