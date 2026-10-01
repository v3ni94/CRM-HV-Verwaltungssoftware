"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type PostingConfig = {
  manager_ledger_id: string;
  manager_receivable_account_id: string;
  manager_revenue_account_id: string;
  manager_vat_account_id: string | null;
  payer_expense_account_number: string;
  payer_payable_account_number: string;
  payer_vat_account_number: string | null;
};

export type LedgerChoice = { id: string; label: string };
type AccountChoice = { id: string; number: string; name: string; active: boolean };

const SIX_DIGITS = /^[0-9]{6}$/;

/** M13-07 (T04-Rest): Kontenzuordnung der Honorarbuchung, `GET/PUT /accounting/admin-fee-posting-config`.
 *  Es gibt keinen Standard: ohne Zuordnung entsteht kein Buchungsentwurf. Verwalterseite mit
 *  Konten aus dem Kontenrahmen des gewählten Buchungskreises (nur Verwalter-Rechtsträger, die API
 *  prüft das), Zahlerseite mit sechsstelligen Kontonummern, die je Buchungskreis des Schuldners
 *  aufgelöst werden. Steuerliche Behandlung offen (docs/OPEN_QUESTIONS.md T04-01), Prüfung durch
 *  Steuerberater. Speichern nur mit accounting:approve. Die Buchung selbst bleibt hinter G1. */
export function AdminFeePostingConfigForm({
  ledgers,
  initial,
  canUpdate,
}: {
  ledgers: LedgerChoice[];
  initial: PostingConfig | null;
  canUpdate: boolean;
}) {
  const t = useTranslations("AdminFeePostingConfig");
  const [ledger, setLedger] = useState(initial?.manager_ledger_id ?? "");
  const [receivable, setReceivable] = useState(initial?.manager_receivable_account_id ?? "");
  const [revenue, setRevenue] = useState(initial?.manager_revenue_account_id ?? "");
  const [vat, setVat] = useState(initial?.manager_vat_account_id ?? "");
  const [expenseNo, setExpenseNo] = useState(initial?.payer_expense_account_number ?? "");
  const [payableNo, setPayableNo] = useState(initial?.payer_payable_account_number ?? "");
  const [vatNo, setVatNo] = useState(initial?.payer_vat_account_number ?? "");
  const [accounts, setAccounts] = useState<AccountChoice[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ledger) {
      setAccounts([]);
      return;
    }
    let active = true;
    setLoadError(null);
    void bff<AccountChoice[]>(`/api/bff/accounting/ledgers/${ledger}/accounts`).then((res) => {
      if (!active) return;
      if (res.ok) setAccounts(res.data.filter((a) => a.active));
      else {
        setAccounts([]);
        setLoadError(res.message);
      }
    });
    return () => {
      active = false;
    };
  }, [ledger]);

  const managerIds = [receivable, revenue, ...(vat ? [vat] : [])];
  const payerNumbers = [expenseNo.trim(), payableNo.trim(), ...(vatNo.trim() ? [vatNo.trim()] : [])];
  const managerDistinct = new Set(managerIds).size === managerIds.length;
  const payerDistinct = new Set(payerNumbers).size === payerNumbers.length;
  const numbersValid =
    SIX_DIGITS.test(expenseNo.trim()) && SIX_DIGITS.test(payableNo.trim()) && (!vatNo.trim() || SIX_DIGITS.test(vatNo.trim()));
  const valid = Boolean(ledger && receivable && revenue) && managerDistinct && payerDistinct && numbersValid;

  const onLedger = (value: string) => {
    setLedger(value);
    setReceivable("");
    setRevenue("");
    setVat("");
  };

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!valid) return;
    setBusy(true);
    setMessage(null);
    setError(null);
    const body: PostingConfig = {
      manager_ledger_id: ledger,
      manager_receivable_account_id: receivable,
      manager_revenue_account_id: revenue,
      manager_vat_account_id: vat || null,
      payer_expense_account_number: expenseNo.trim(),
      payer_payable_account_number: payableNo.trim(),
      payer_vat_account_number: vatNo.trim() || null,
    };
    const res = await bff<PostingConfig>("/api/bff/accounting/admin-fee-posting-config", {
      method: "PUT",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (res.ok) setMessage(t("saved"));
    else setError(res.message);
  }

  const accountSelect = (label: string, value: string, onChange: (v: string) => void, optional = false) => (
    <label className={ui.label}>
      {label}
      <select className={ui.input} value={value} disabled={!canUpdate || !ledger} onChange={(e) => onChange(e.target.value)}>
        <option value="">{optional ? t("none") : t("choose")}</option>
        {accounts.map((a) => (
          <option key={a.id} value={a.id}>
            {a.number} {a.name}
          </option>
        ))}
      </select>
    </label>
  );

  const numberInput = (label: string, value: string, onChange: (v: string) => void, optional = false) => (
    <label className={ui.label}>
      {label}
      <input
        className={ui.input}
        inputMode="numeric"
        maxLength={6}
        value={value}
        disabled={!canUpdate}
        aria-invalid={value.trim() !== "" && !SIX_DIGITS.test(value.trim())}
        placeholder={optional ? t("optional") : ""}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );

  return (
    <form onSubmit={save} className={ui.card} aria-labelledby="admin-fee-posting-config-title">
      <div className="flex flex-col gap-3">
        <h2 id="admin-fee-posting-config-title" className={ui.h2}>
          {t("title")}
        </h2>
        <p className={ui.help}>{t("description")}</p>
        <p className="text-xs text-warning-fg">{t("gateHint")}</p>
        {initial === null ? <p className={ui.notice}>{t("notConfigured")}</p> : null}
        <label className={ui.label}>
          {t("ledger")}
          <select className={ui.input} value={ledger} disabled={!canUpdate} onChange={(e) => onLedger(e.target.value)}>
            <option value="">{t("choose")}</option>
            {ledgers.map((l) => (
              <option key={l.id} value={l.id}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
        <p className={ui.help}>{t("ledgerHint")}</p>
        <h3 className="text-sm font-semibold">{t("managerSide")}</h3>
        <div className="grid gap-2 sm:grid-cols-3">
          {accountSelect(t("receivable"), receivable, setReceivable)}
          {accountSelect(t("revenue"), revenue, setRevenue)}
          {accountSelect(t("vat"), vat, setVat, true)}
        </div>
        {loadError ? (
          <p role="alert" className={ui.alert}>
            {loadError}
          </p>
        ) : null}
        {!managerDistinct ? <p className={ui.error}>{t("managerDistinct")}</p> : null}
        <h3 className="text-sm font-semibold">{t("payerSide")}</h3>
        <p className={ui.help}>{t("payerHint")}</p>
        <div className="grid gap-2 sm:grid-cols-3">
          {numberInput(t("expenseNo"), expenseNo, setExpenseNo)}
          {numberInput(t("payableNo"), payableNo, setPayableNo)}
          {numberInput(t("vatNo"), vatNo, setVatNo, true)}
        </div>
        {!numbersValid ? <p className={ui.error}>{t("numbersInvalid")}</p> : null}
        {!payerDistinct ? <p className={ui.error}>{t("payerDistinct")}</p> : null}
        <p className={ui.notice}>{t("taxHint")}</p>
        {!canUpdate ? <p className={ui.help}>{t("readOnly")}</p> : null}
        {canUpdate ? (
          <div className={ui.formActions}>
            <button type="submit" className={ui.primary} disabled={busy || !valid}>
              {t("save")}
            </button>
          </div>
        ) : null}
        {message ? <span className="text-xs text-success-fg">{message}</span> : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
      </div>
    </form>
  );
}
