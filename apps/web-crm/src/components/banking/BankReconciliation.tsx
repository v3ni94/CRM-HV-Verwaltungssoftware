"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { bankAccountLabel, toCents, type BankAccountOption } from "./bankTypes";

export type ReconciliationRow = {
  statement_id: string;
  statement_ref: string | null;
  closing_date: string | null;
  opening_balance: string | null;
  movements: string;
  closing_balance: string | null;
  statement_difference: string | null;
  ledger_balance: string | null;
  ledger_difference: string | null;
};

/** Bank reconciliation per statement (B09, `GET /banking/accounts/{id}/reconciliation`):
 *  opening balance plus movements against the closing balance of the statement and, when the
 *  account is linked to a ledger account, against the posted ledger balance at the closing
 *  date. Read only; a difference is a finding to clear, never corrected here. */
export function BankReconciliation() {
  const t = useTranslations("Bank.reconciliation");
  const [accounts, setAccounts] = useState<BankAccountOption[]>([]);
  const [accountId, setAccountId] = useState("");
  const [rows, setRows] = useState<ReconciliationRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      const res = await bff<BankAccountOption[]>("/api/bff/banking/accounts");
      if (res.ok) setAccounts(res.data);
      else setError(res.message);
    })();
  }, []);

  useEffect(() => {
    if (!accountId) {
      setRows(null);
      return;
    }
    let cancelled = false;
    (async () => {
      setBusy(true);
      setError(null);
      const res = await bff<ReconciliationRow[]>(`/api/bff/banking/accounts/${accountId}/reconciliation`);
      if (cancelled) return;
      setBusy(false);
      if (res.ok) setRows(res.data);
      else {
        setRows([]);
        setError(res.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accountId]);

  const diffClass = (value: string | null) => (value !== null && toCents(value) !== 0 ? "num text-danger-fg font-medium" : "num");
  const findings = (rows ?? []).filter((r) => toCents(r.statement_difference) !== 0 || toCents(r.ledger_difference) !== 0).length;

  return (
    <section className="flex flex-col gap-3" data-testid="bank-reconciliation">
      <label className="flex max-w-md flex-col gap-1">
        <span className={ui.label}>{t("account")}</span>
        <select className={ui.input} value={accountId} onChange={(e) => setAccountId(e.target.value)}>
          <option value="">{t("chooseAccount")}</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {bankAccountLabel(a)}
            </option>
          ))}
        </select>
      </label>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {busy ? <p className="text-sm text-muted">{t("loading")}</p> : null}
      {rows !== null && rows.length === 0 && !busy ? <EmptyState title={t("empty")} /> : null}
      {rows && rows.length > 0 ? (
        <>
          <p className={findings > 0 ? ui.warning : ui.success} data-testid="reconciliation-summary">
            {findings > 0 ? t("findings", { count: findings }) : t("noFindings")}
          </p>
          <div className="overflow-x-auto">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th>{t("statement")}</th>
                  <th>{t("closingDate")}</th>
                  <th className="num">{t("opening")}</th>
                  <th className="num">{t("movements")}</th>
                  <th className="num">{t("closing")}</th>
                  <th className="num">{t("statementDifference")}</th>
                  <th className="num">{t("ledgerBalance")}</th>
                  <th className="num">{t("ledgerDifference")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.statement_id}>
                    <td>{r.statement_ref ?? r.statement_id}</td>
                    <td>{r.closing_date ? formatDate(r.closing_date) : ""}</td>
                    <td className="num">{r.opening_balance !== null ? formatEur(r.opening_balance) : ""}</td>
                    <td className="num">{formatEur(r.movements)}</td>
                    <td className="num">{r.closing_balance !== null ? formatEur(r.closing_balance) : ""}</td>
                    <td className={diffClass(r.statement_difference)}>{r.statement_difference !== null ? formatEur(r.statement_difference) : t("na")}</td>
                    <td className="num">{r.ledger_balance !== null ? formatEur(r.ledger_balance) : t("na")}</td>
                    <td className={diffClass(r.ledger_difference)}>{r.ledger_difference !== null ? formatEur(r.ledger_difference) : t("na")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
      <p className="text-xs text-muted">{t("note")}</p>
    </section>
  );
}
