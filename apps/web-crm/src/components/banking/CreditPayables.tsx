"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";
import { today } from "@/lib/today";

export type CreditPayableSettings = {
  mode: "off" | "subledger" | "reclass";
  four_eyes_required: boolean;
  creditor_account_number: string | null;
  owner_debit_account_number: string | null;
  deposit_debit_account_number: string | null;
  modes: string[];
  decision_ref: string;
  note: string;
};
export type CreditPayableCandidate = {
  source_type: string;
  source_id: string;
  contract_id: string | null;
  ledger_id: string;
  amount: string;
  label: string;
  reference_date: string | null;
  source_entry_id: string | null;
  payout_reason: string;
};
export type CreditPayableRow = {
  id: string;
  source_type: string;
  source_id: string;
  contract_id: string | null;
  amount: string;
  variant: string;
  status: string;
  state: string;
  remaining: string | null;
  reclass_entry_id: string | null;
  payment_order_id: string | null;
  warnings: { code: string; message: string }[];
};
type Option = { id: string; holder: string | null; iban_suffix: string };
type Options = { payees: Option[]; bank_accounts: Option[] };

const BASE = "/api/bff/accounting/credit-payables";
const ACCOUNT_FIELDS = ["creditor_account_number", "owner_debit_account_number", "deposit_debit_account_number"] as const;

/** Payables from statement credits (AE22, Q01-01 open): the tenant switch is off by default.
 *  Proposal, release by a second person (G3), payout order without invoice (G2 and G3, two
 *  approvals on the order) and withdrawal. Nothing here posts or produces a payment file. */
export function CreditPayables() {
  const t = useTranslations("CreditPayables");
  const [settings, setSettings] = useState<CreditPayableSettings | null>(null);
  const [draft, setDraft] = useState<CreditPayableSettings | null>(null);
  const [candidates, setCandidates] = useState<CreditPayableCandidate[]>([]);
  const [rows, setRows] = useState<CreditPayableRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [ordering, setOrdering] = useState<{ id: string; options: Options; payee: string; bank: string } | null>(null);
  const [executionDate, setExecutionDate] = useState<string>(today());
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [s, c, r] = await Promise.all([
      bff<CreditPayableSettings>(`${BASE}/settings`),
      bff<CreditPayableCandidate[]>(`${BASE}/candidates`),
      bff<CreditPayableRow[]>(BASE),
    ]);
    if (s.ok) {
      setSettings(s.data);
      setDraft(s.data);
    }
    if (c.ok) setCandidates(c.data);
    if (r.ok) setRows(r.data);
    const failed = [s, c, r].find((x) => !x.ok);
    setError(failed && !failed.ok ? failed.message : null);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async (path: string, init: RequestInit, done: string) => {
    setBusy(true);
    const res = await bff<unknown>(path, init);
    setBusy(false);
    if (res.ok) {
      setInfo(done);
      setError(null);
      await load();
      return true;
    }
    setError(res.message);
    return false;
  };

  const saveSettings = async () => {
    if (!draft) return;
    const body: Record<string, unknown> = { mode: draft.mode, four_eyes_required: draft.four_eyes_required };
    for (const field of ACCOUNT_FIELDS) if (draft[field]) body[field] = draft[field];
    await run(`${BASE}/settings`, { method: "PUT", body: JSON.stringify(body) }, t("saved"));
  };

  const propose = (c: CreditPayableCandidate) =>
    run(
      BASE,
      {
        method: "POST",
        body: JSON.stringify({ source_type: c.source_type, source_id: c.source_id, contract_id: c.contract_id }),
      },
      t("proposed"),
    );

  const openOrder = async (row: CreditPayableRow) => {
    const res = await bff<Options>(`${BASE}/${row.id}/payout-options`);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setOrdering({
      id: row.id,
      options: res.data,
      payee: res.data.payees[0]?.id ?? "",
      bank: res.data.bank_accounts[0]?.id ?? "",
    });
  };

  const createOrder = async () => {
    if (!ordering || !ordering.payee || !ordering.bank) return;
    const ok = await run(
      `${BASE}/${ordering.id}/payment-order`,
      {
        method: "POST",
        body: JSON.stringify({
          contact_bank_account_id: ordering.payee,
          property_bank_account_id: ordering.bank,
          execution_date: executionDate,
        }),
      },
      t("orderCreated"),
    );
    if (ok) setOrdering(null);
  };

  const withdraw = (row: CreditPayableRow) => {
    const reason = window.prompt(t("withdrawReason"));
    if (!reason || reason.trim().length < 3) return;
    void run(`${BASE}/${row.id}/withdraw`, { method: "POST", body: JSON.stringify({ reason }) }, t("withdrawn"));
  };

  if (!settings || !draft) {
    return error ? (
      <p role="alert" className={ui.alert}>
        {error}
      </p>
    ) : (
      <p className="text-sm text-muted">{t("loading")}</p>
    );
  }
  const off = settings.mode === "off";
  return (
    <section className={ui.card} aria-label={t("title")}>
      <h2 className="text-base font-semibold">{t("title")}</h2>
      <p className={ui.notice}>{t("notice", { ref: settings.decision_ref })}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {info ? (
        <p role="status" className={ui.success}>
          {info}
        </p>
      ) : null}

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className={ui.label}>{t("mode")}</span>
          <select
            className={ui.input}
            value={draft.mode}
            onChange={(e) => setDraft({ ...draft, mode: e.target.value as CreditPayableSettings["mode"] })}
          >
            {settings.modes.map((m) => (
              <option key={m} value={m}>
                {t(`modes.${m}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={draft.four_eyes_required}
            onChange={(e) => setDraft({ ...draft, four_eyes_required: e.target.checked })}
          />
          {t("fourEyes")}
        </label>
        {ACCOUNT_FIELDS.map((field) => (
          <label key={field} className="block">
            <span className={ui.label}>{t(`accounts.${field}`)}</span>
            <input
              className={ui.input}
              inputMode="numeric"
              maxLength={6}
              value={draft[field] ?? ""}
              onChange={(e) => setDraft({ ...draft, [field]: e.target.value || null })}
            />
          </label>
        ))}
      </div>
      <p className={ui.help}>{t(`modeHelp.${draft.mode}`)}</p>
      <div className="mt-2">
        <button type="button" className={ui.secondary} disabled={busy} onClick={() => void saveSettings()}>
          {t("save")}
        </button>
      </div>

      <h3 className="mt-4 text-sm font-semibold">{t("candidates")}</h3>
      {candidates.length === 0 ? <p className="text-sm text-muted">{t("noCandidates")}</p> : null}
      {candidates.length > 0 ? (
        <div className={ui.tableScroll}>
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("source")}</th>
                <th>{t("date")}</th>
                <th className="num">{t("amount")}</th>
                <th>
                  <span className="sr-only">{t("actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c) => (
                <tr key={`${c.source_type}:${c.source_id}:${c.contract_id ?? "-"}`}>
                  <td>{c.label}</td>
                  <td>{c.reference_date ? formatDate(c.reference_date) : ""}</td>
                  <td className="num">{formatEur(c.amount)}</td>
                  <td>
                    <button
                      type="button"
                      className={ui.buttonSm}
                      disabled={off || busy}
                      title={off ? t("offHint") : undefined}
                      onClick={() => void propose(c)}
                    >
                      {t("propose")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <h3 className="mt-4 text-sm font-semibold">{t("rows")}</h3>
      {rows.length === 0 ? <p className="text-sm text-muted">{t("noRows")}</p> : null}
      {rows.length > 0 ? (
        <div className={ui.tableScroll}>
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("source")}</th>
                <th>{t("variant")}</th>
                <th>{t("state")}</th>
                <th className="num">{t("amount")}</th>
                <th>
                  <span className="sr-only">{t("actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    {t(`sources.${r.source_type}`)}
                    {r.warnings.map((w) => (
                      <span key={w.code} className="block text-xs text-warning-fg">
                        {w.message}
                      </span>
                    ))}
                  </td>
                  <td>{t(`modes.${r.variant}`)}</td>
                  <td>{t(`states.${r.state}`)}</td>
                  <td className="num">{formatEur(r.remaining ?? r.amount)}</td>
                  <td className="flex flex-wrap gap-1">
                    {r.status === "proposed" ? (
                      <button
                        type="button"
                        className={ui.buttonSm}
                        disabled={busy}
                        onClick={() => void run(`${BASE}/${r.id}/release`, { method: "POST", body: "{}" }, t("released"))}
                      >
                        {t("release")}
                      </button>
                    ) : null}
                    {r.state === "open" || r.state === "partially_paid" ? (
                      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void openOrder(r)}>
                        {t("order")}
                      </button>
                    ) : null}
                    {r.status !== "withdrawn" ? (
                      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => withdraw(r)}>
                        {t("withdraw")}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {ordering ? (
        <div className="mt-3 grid gap-3 sm:grid-cols-3" role="group" aria-label={t("order")}>
          <label className="block">
            <span className={ui.label}>{t("payee")}</span>
            <select
              className={ui.input}
              value={ordering.payee}
              onChange={(e) => setOrdering({ ...ordering, payee: e.target.value })}
            >
              {ordering.options.payees.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.holder ?? t("payee")} …{p.iban_suffix}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className={ui.label}>{t("bankAccount")}</span>
            <select
              className={ui.input}
              value={ordering.bank}
              onChange={(e) => setOrdering({ ...ordering, bank: e.target.value })}
            >
              {ordering.options.bank_accounts.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.holder ?? ""} …{b.iban_suffix}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className={ui.label}>{t("executionDate")}</span>
            <input
              type="date"
              className={ui.input}
              value={executionDate}
              onChange={(e) => setExecutionDate(e.target.value)}
            />
          </label>
          {ordering.options.payees.length === 0 || ordering.options.bank_accounts.length === 0 ? (
            <p className={ui.error}>{t("noOptions")}</p>
          ) : null}
          <div className={ui.formActions}>
            <button
              type="button"
              className={ui.primary}
              disabled={busy || !ordering.payee || !ordering.bank}
              onClick={() => void createOrder()}
            >
              {t("createOrder")}
            </button>
            <button type="button" className={ui.secondary} onClick={() => setOrdering(null)}>
              {t("cancel")}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
