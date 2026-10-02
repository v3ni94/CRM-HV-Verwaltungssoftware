"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import type { LedgerAccountOption } from "./JournalEntryForm";
import { useBusy } from "@/lib/use-busy";

const FIELDS = ["capital_gains_tax_account_id", "solidarity_tax_account_id", "church_tax_account_id"] as const;
type Field = (typeof FIELDS)[number];
type Config = Record<Field, string | null>;
const TAX_KEY: Record<Field, string> = {
  capital_gains_tax_account_id: "capital_gains_tax",
  solidarity_tax_account_id: "solidarity_tax",
  church_tax_account_id: "church_tax",
};
const EXCLUDED = new Set(["bank", "cash", "reserve", "revenue"]);

/** Tax accounts per ledger for withholdings on credit interest (P01-01, AE05). Without an
 *  account the withholding cannot be entered; no tax rate is maintained here. */
export function InterestTaxConfig({ ledgerId, accounts }: { ledgerId: string; accounts: LedgerAccountOption[] }) {
  const { guard } = useBusy();
  const t = useTranslations("Bookkeeping");
  const [config, setConfig] = useState<Config>({ capital_gains_tax_account_id: null, solidarity_tax_account_id: null, church_tax_account_id: null });
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const url = `/api/bff/accounting/ledgers/${ledgerId}/interest-tax-config`;
  const options = accounts.filter((a) => a.active && !EXCLUDED.has(a.category));

  useEffect(() => {
    void bff<Config>(url).then((res) => {
      if (res.ok) setConfig(res.data);
    });
  }, [url]);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    const body = Object.fromEntries(FIELDS.map((f) => [f, config[f] || null]));
    const res = await bff<Config>(url, { method: "PUT", body: JSON.stringify(body) });
    setMessage(res.ok ? { ok: true, text: t("entry.interestTax.saved") } : { ok: false, text: res.message });
  };

  return (
    <form onSubmit={guard(save)} className={`${ui.card} flex flex-col gap-3`} aria-label={t("entry.interestTax.title")}>
      <h3 className="text-sm font-semibold">{t("entry.interestTax.title")}</h3>
      <p className={ui.help}>{t("entry.interestTax.help")}</p>
      <div className="grid gap-3 sm:grid-cols-3">
        {FIELDS.map((field) => (
          <label key={field} className="flex flex-col gap-1">
            <span className={ui.label}>{t(`entry.taxes.${TAX_KEY[field]}`)}</span>
            <select className={ui.input} value={config[field] ?? ""} onChange={(e) => setConfig((c) => ({ ...c, [field]: e.target.value || null }))}>
              <option value="">{t("entry.interestTax.none")}</option>
              {options.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.number} {a.name}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <div className={ui.formActions}>
        <button type="submit" className={ui.primary}>
          {t("entry.interestTax.save")}
        </button>
      </div>
      {message ? (
        <p role={message.ok ? "status" : "alert"} className={message.ok ? ui.success : ui.error}>
          {message.text}
        </p>
      ) : null}
    </form>
  );
}
