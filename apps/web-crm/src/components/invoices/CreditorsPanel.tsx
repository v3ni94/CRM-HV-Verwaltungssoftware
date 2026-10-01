"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Option = { id: string; label: string };
type Creditor = { account_id: string; number: string; name: string; balance: string; open_items: number; open_amount: string; invoices: number };
type Movement = { entry_id: string; number: string; booking_date: string; text: string | null; debit: string; credit: string; balance: string };
type Statement = { opening_balance: string; closing_balance: string; movements: Movement[] };

/** M14-08: creditors of a ledger with balance and open payables, statement per creditor. Read only. */
export function CreditorsPanel({ ledgers }: { ledgers: Option[] }) {
  const t = useTranslations("Creditors");
  const [ledger, setLedger] = useState(ledgers[0]?.id ?? "");
  const [rows, setRows] = useState<Creditor[] | null>(null);
  const [selected, setSelected] = useState<Creditor | null>(null);
  const [statement, setStatement] = useState<Statement | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ledger) return;
    setRows(null);
    setSelected(null);
    setStatement(null);
    void bff<Creditor[]>(`/api/bff/accounting/ledgers/${ledger}/creditors`).then((res) => {
      if (res.ok) setRows(res.data);
      else setError(res.message);
    });
  }, [ledger]);

  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const load = (id: string) =>
    bff<Creditor[]>(`/api/bff/accounting/ledgers/${id}/creditors`).then((res) => {
      if (res.ok) setRows(res.data);
      else setError(res.message);
    });
  // M10-05: Kreditorenkonten für alle Dienstleisterverhältnisse anlegen und verknüpfen.
  const sync = async () => {
    setSyncing(true);
    setError(null);
    setSyncMessage(null);
    const res = await bff<{ created: number; linked: number }>(`/api/bff/accounting/ledgers/${ledger}/sync-creditors`, { method: "POST" });
    setSyncing(false);
    if (!res.ok) return setError(res.message);
    setSyncMessage(t("syncDone", { created: res.data.created, linked: res.data.linked }));
    await load(ledger);
  };
  const open = async (c: Creditor) => {
    setSelected(c);
    setStatement(null);
    const res = await bff<Statement>(`/api/bff/accounting/ledgers/${ledger}/creditors/${c.account_id}/statement`);
    if (res.ok) setStatement(res.data);
    else setError(res.message);
  };

  return (
    <div className="flex flex-col gap-4">
      <label className="flex max-w-sm flex-col gap-1">
        <span className={ui.label}>{t("ledger")}</span>
        <select className={ui.input} value={ledger} onChange={(e) => setLedger(e.target.value)}>
          {ledgers.map((l) => (
            <option key={l.id} value={l.id}>{l.label}</option>
          ))}
        </select>
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={ui.button} onClick={() => void sync()} disabled={syncing || !ledger}>{t("sync")}</button>
        <span className={ui.help}>{t("syncHint")}</span>
      </div>
      <p className={ui.help} data-testid="creditor-default-rule-hint">{t("defaultRuleHint")}</p>
      {syncMessage ? <p className={ui.success} role="status">{syncMessage}</p> : null}
      {error ? <p className={ui.alert} role="alert">{error}</p> : null}
      {rows === null ? null : rows.length === 0 ? (
        <p className={ui.notice}>{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("number")}</th>
                <th>{t("name")}</th>
                <th className="num">{t("balance")}</th>
                <th className="num">{t("openItems")}</th>
                <th className="num">{t("openAmount")}</th>
                <th className="num">{t("invoices")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.account_id}>
                  <td>
                    <button type="button" className="font-medium hover:underline" onClick={() => void open(c)}>{c.number}</button>
                  </td>
                  <td>{c.name}</td>
                  <td className="num">{formatEur(c.balance)}</td>
                  <td className="num">{c.open_items}</td>
                  <td className="num">{formatEur(c.open_amount)}</td>
                  <td className="num">{c.invoices}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selected && statement ? (
        <section className={ui.card} data-testid="creditor-statement">
          <h2 className={ui.title}>{t("statementTitle", { number: selected.number, name: selected.name })}</h2>
          <p className={ui.small}>
            {t("opening")}: {formatEur(statement.opening_balance)} · {t("closing")}: {formatEur(statement.closing_balance)}
          </p>
          {statement.movements.length === 0 ? (
            <p className={ui.small}>{t("noMovements")}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="mhvp-table">
                <thead>
                  <tr>
                    <th>{t("date")}</th>
                    <th>{t("entry")}</th>
                    <th>{t("text")}</th>
                    <th className="num">{t("debit")}</th>
                    <th className="num">{t("credit")}</th>
                    <th className="num">{t("runningBalance")}</th>
                  </tr>
                </thead>
                <tbody>
                  {statement.movements.map((m) => (
                    <tr key={`${m.entry_id}-${m.number}-${m.debit}-${m.credit}`}>
                      <td>{formatDate(m.booking_date)}</td>
                      <td>{m.number}</td>
                      <td>{m.text ?? ""}</td>
                      <td className="num">{formatEur(m.debit)}</td>
                      <td className="num">{formatEur(m.credit)}</td>
                      <td className="num">{formatEur(m.balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
