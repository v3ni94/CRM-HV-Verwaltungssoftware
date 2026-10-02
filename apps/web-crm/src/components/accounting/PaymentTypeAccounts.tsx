"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Mapping = { payment_type_code: string; account_id: string; account_number: string; account_name: string };
type Option = { id: string; number: string; name: string; category: string; active: boolean };

/** GAF-05: revenue account per payment type (PUT payment-type-accounts). The API accepts
 *  revenue accounts, for the reserved code vat_output a tax account. */
export function PaymentTypeAccounts({ ledgerId, accounts }: { ledgerId: string; accounts: Option[] }) {
  const t = useTranslations("LedgerExtras.paymentType");
  const [code, setCode] = useState("");
  const [accountId, setAccountId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [mappings, setMappings] = useState<Mapping[]>([]);
  useEffect(() => {
    let alive = true;
    void bff<Mapping[]>(`/api/bff/accounting/ledgers/${ledgerId}/payment-type-accounts`).then((res) => {
      if (alive && res.ok && Array.isArray(res.data)) setMappings(res.data);
    });
    return () => {
      alive = false;
    };
  }, [ledgerId]);
  const wanted = code.trim() === "vat_output" ? "tax" : "revenue";
  const choices = accounts.filter((a) => a.active && a.category === wanted);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    const res = await bff(`/api/bff/accounting/ledgers/${ledgerId}/payment-type-accounts`, {
      method: "PUT",
      body: JSON.stringify({ payment_type_code: code.trim(), account_id: accountId }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setSaved(true);
    const acc = accounts.find((a) => a.id === accountId);
    if (acc) {
      const row = { payment_type_code: code.trim(), account_id: acc.id, account_number: acc.number, account_name: acc.name };
      setMappings((m) => [...m.filter((x) => x.payment_type_code !== row.payment_type_code), row].sort((a, b) => a.payment_type_code.localeCompare(b.payment_type_code)));
    }
  };
  return (
    <form onSubmit={submit} className={`${ui.card} flex flex-col gap-3`} aria-label={t("title")}>
      <h3 className="text-sm font-semibold">{t("title")}</h3>
      <p className={ui.help}>{t("help")}</p>
      {mappings.length ? (
        <ul className="text-sm" aria-label={t("existing")} data-testid="payment-type-mappings">
          {mappings.map((m) => (
            <li key={m.payment_type_code}>
              {m.payment_type_code}: {m.account_number} {m.account_name}
            </li>
          ))}
        </ul>
      ) : (
        <p className={ui.help}>{t("noneYet")}</p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("code")}</span>
          <input required maxLength={63} className={ui.input} value={code} onChange={(e) => { setCode(e.target.value); setAccountId(""); }} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("account")}</span>
          <select required className={ui.input} value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">{t("choose")}</option>
            {choices.map((a) => (
              <option key={a.id} value={a.id}>
                {a.number} {a.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className={ui.formActions}>
        <button type="submit" className={ui.primary} disabled={busy || !code.trim() || !accountId}>
          {t("save")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
      {saved ? (
        <p role="status" className={ui.success}>
          {t("saved")}
        </p>
      ) : null}
    </form>
  );
}
