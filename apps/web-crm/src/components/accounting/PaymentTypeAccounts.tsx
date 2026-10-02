"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

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
  };
  return (
    <form onSubmit={submit} className={`${ui.card} flex flex-col gap-3`} aria-label={t("title")}>
      <h3 className="text-sm font-semibold">{t("title")}</h3>
      <p className={ui.help}>{t("help")}</p>
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
