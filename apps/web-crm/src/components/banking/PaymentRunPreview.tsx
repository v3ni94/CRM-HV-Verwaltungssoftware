"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";
import { today } from "@/lib/today";

type PreviewInvoice = {
  invoice_id: string;
  number: string;
  payee: string;
  iban_suffix: string | null;
  due_date: string;
  overdue: boolean;
  remaining: string;
  eligible: boolean;
  block_reason: string | null;
};
type PreviewAccount = {
  id: string;
  iban_suffix: string;
  holder: string;
  limits: { single_order_limit: string | null; daily_limit: string | null };
};
type PreviewGroup = {
  legal_entity_id: string;
  legal_entity_name: string;
  bank_accounts: PreviewAccount[];
  invoices: PreviewInvoice[];
  total: string;
};
type PreviewDebit = {
  run_id: string;
  status: string;
  collection_date: string;
  control_sum: string;
  transaction_count: number;
  pre_notifications_missing: number;
};
export type PaymentRunPreviewData = {
  as_of: string;
  until: string;
  legal_entities: PreviewGroup[];
  direct_debit_runs: PreviewDebit[];
  verification_of_payee: string;
};
type CreateResult = {
  created: { id: string }[];
  failed: { invoice_id: string; detail: string }[];
  limit_warnings: string[];
};

/** Payment run preview (M15-03): payable invoices per legal entity with the ordering accounts,
 *  due direct debit runs, bulk creation of draft orders. Nothing is approved or exported here;
 *  every order still needs two approvals and the payment file needs G2. */
export function PaymentRunPreview() {
  const t = useTranslations("PaymentRun");
  const [data, setData] = useState<PaymentRunPreviewData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [accounts, setAccounts] = useState<Record<string, string>>({});
  const [executionDate, setExecutionDate] = useState<string>(today());
  const [result, setResult] = useState<CreateResult | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const res = await bff<PaymentRunPreviewData>("/api/bff/accounting/payment-runs/preview");
    if (res.ok) {
      setData(res.data);
      setError(null);
    } else setError(res.message);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const create = async () => {
    if (!data) return;
    const items = data.legal_entities.flatMap((g) => {
      const account = accounts[g.legal_entity_id] ?? g.bank_accounts[0]?.id;
      return g.invoices
        .filter((i) => i.eligible && selected[i.invoice_id] && account)
        .map((i) => ({ invoice_id: i.invoice_id, property_bank_account_id: account as string }));
    });
    if (items.length === 0) return;
    setBusy(true);
    const res = await bff<CreateResult>("/api/bff/accounting/payment-runs/orders", {
      method: "POST",
      body: JSON.stringify({ execution_date: executionDate, items }),
    });
    setBusy(false);
    if (res.ok) {
      setResult(res.data);
      setSelected({});
      await load();
    } else setError(res.message);
  };

  if (error && !data) {
    return (
      <p role="alert" className={ui.alert}>
        {error}
      </p>
    );
  }
  if (!data) return <p className="text-sm text-muted">{t("loading")}</p>;
  const count = Object.values(selected).filter(Boolean).length;
  return (
    <div className="flex flex-col gap-4">
      <p className={ui.notice}>{t("notice")}</p>
      <p className={ui.help} data-testid="vop-note">
        {data.verification_of_payee}
      </p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {result ? (
        <div className={ui.success} role="status">
          {t("created", { n: result.created.length, failed: result.failed.length })}
          {result.failed.map((f) => (
            <span key={f.invoice_id} className="block text-xs">
              {f.detail}
            </span>
          ))}
          {result.limit_warnings.map((w) => (
            <span key={w} className="block text-xs">
              {t("limitWarning")}: {w}
            </span>
          ))}
        </div>
      ) : null}
      {data.legal_entities.length === 0 ? <p className="text-sm text-muted">{t("empty")}</p> : null}
      {data.legal_entities.map((g) => (
        <section key={g.legal_entity_id} className={ui.card} aria-label={g.legal_entity_name}>
          <h2 className="text-base font-semibold">{g.legal_entity_name}</h2>
          <p className="text-sm text-muted">{t("total", { amount: formatEur(g.total) })}</p>
          {g.bank_accounts.length === 0 ? (
            <p className={ui.error}>{t("noAccount")}</p>
          ) : (
            <label className="mt-2 block max-w-sm">
              <span className={ui.label}>{t("account")}</span>
              <select
                className={ui.input}
                value={accounts[g.legal_entity_id] ?? g.bank_accounts[0]?.id ?? ""}
                onChange={(e) => setAccounts({ ...accounts, [g.legal_entity_id]: e.target.value })}
              >
                {g.bank_accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.holder} …{a.iban_suffix}
                    {a.limits.daily_limit ? ` (${t("dailyLimit")} ${formatEur(a.limits.daily_limit)})` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="mt-2 overflow-x-auto">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th>
                    <span className="sr-only">{t("select")}</span>
                  </th>
                  <th>{t("invoice")}</th>
                  <th>{t("payee")}</th>
                  <th>{t("due")}</th>
                  <th className="num">{t("remaining")}</th>
                  <th>{t("check")}</th>
                </tr>
              </thead>
              <tbody>
                {g.invoices.map((i) => (
                  <tr key={i.invoice_id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={t("selectInvoice", { number: i.number })}
                        disabled={!i.eligible}
                        checked={Boolean(selected[i.invoice_id])}
                        onChange={(e) => setSelected({ ...selected, [i.invoice_id]: e.target.checked })}
                      />
                    </td>
                    <td>{i.number}</td>
                    <td>
                      {i.payee}
                      {i.iban_suffix ? <span className="ml-1 text-xs text-muted">…{i.iban_suffix}</span> : null}
                    </td>
                    <td>
                      {formatDate(i.due_date)}
                      {i.overdue ? <span className="ml-1 text-xs text-danger-fg">{t("overdue")}</span> : null}
                    </td>
                    <td className="num">{formatEur(i.remaining)}</td>
                    <td className="text-xs">{i.block_reason ?? t("ok")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
      {data.legal_entities.length > 0 ? (
        <div className={ui.formActions}>
          <label>
            <span className={ui.label}>{t("executionDate")}</span>
            <input
              type="date"
              className={ui.input}
              value={executionDate}
              onChange={(e) => setExecutionDate(e.target.value)}
            />
          </label>
          <button type="button" className={ui.primary} onClick={create} disabled={busy || count === 0}>
            {t("createOrders", { n: count })}
          </button>
        </div>
      ) : null}
      <section className={ui.card}>
        <h2 className="text-base font-semibold">{t("debits")}</h2>
        {data.direct_debit_runs.length === 0 ? (
          <p className="text-sm text-muted">{t("noDebits")}</p>
        ) : (
          <ul className="text-sm">
            {data.direct_debit_runs.map((r) => (
              <li key={r.run_id}>
                {formatDate(r.collection_date)}: {r.transaction_count} {t("debitCount")}, {formatEur(r.control_sum)}
                {r.pre_notifications_missing > 0
                  ? ` (${t("preNotificationsMissing", { n: r.pre_notifications_missing })})`
                  : ""}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
