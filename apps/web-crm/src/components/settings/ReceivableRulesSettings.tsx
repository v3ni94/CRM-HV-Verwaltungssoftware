"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** M13-01 to M13-03 (docs/rules/M13-01.md to M13-03.md): tenant defaults for the receivable
 *  agent (Sollstellungsagent), `PATCH /tenant/settings`, field `receivable_rules`. Default
 *  off (`enabled=false`); postings stay behind gate G1 (productive bookkeeping) even when a
 *  tenant switches this on for drafting. `payment_interval` (M13-01a) is the tenant default
 *  Zahlweise a new contract's payment schedule takes over when it sets none itself
 *  (`POST /contracts/{id}/schedules`, field `interval` left empty); `null` keeps the previous
 *  behaviour (monthly, no tenant default). */
export type ReceivableRules = {
  enabled: boolean;
  proration_method: "calendar_days" | "thirty_360" | "full_month";
  vat_enabled: boolean;
  payment_interval: "monthly" | "quarterly" | "semiannual" | "annual" | null;
  /** P02-03: monthly preview job, drafts only, default off. */
  monthly_preview_enabled?: boolean;
};

export function ReceivableRulesSettings({ initial, canUpdate }: { initial: ReceivableRules; canUpdate: boolean }) {
  const t = useTranslations("ReceivableRulesSettings");
  const [rules, setRules] = useState<ReceivableRules>(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ receivable_rules: ReceivableRules }>("/api/bff/tenant/settings", {
      method: "PATCH",
      body: JSON.stringify({ receivable_rules: rules }),
    });
    setBusy(false);
    if (res.ok) {
      setRules(res.data.receivable_rules);
      setMessage(t("saved"));
    } else {
      setError(res.message);
    }
  }

  return (
    <form onSubmit={save} className={ui.card} aria-labelledby="receivable-rules-settings-title">
      <div className="flex flex-col gap-3">
        <h2 id="receivable-rules-settings-title" className={ui.h2}>
          {t("title")}
        </h2>
        <p className={ui.help}>{t("description")}</p>
        <p className="text-xs text-warning-fg">{t("gateHint")}</p>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={rules.enabled}
            disabled={!canUpdate}
            onChange={(e) => setRules({ ...rules, enabled: e.target.checked })}
          />
          {t("enabled")}
        </label>
        <label className={ui.label}>
          {t("prorationMethod")}
          <select
            className={ui.input}
            value={rules.proration_method}
            disabled={!canUpdate}
            onChange={(e) => setRules({ ...rules, proration_method: e.target.value as ReceivableRules["proration_method"] })}
          >
            <option value="calendar_days">{t("proration.calendar_days")}</option>
            <option value="thirty_360">{t("proration.thirty_360")}</option>
            <option value="full_month">{t("proration.full_month")}</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={rules.vat_enabled}
            disabled={!canUpdate}
            onChange={(e) => setRules({ ...rules, vat_enabled: e.target.checked })}
          />
          {t("vatEnabled")}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={rules.monthly_preview_enabled ?? false}
            disabled={!canUpdate}
            onChange={(e) => setRules({ ...rules, monthly_preview_enabled: e.target.checked })}
          />
          {t("monthlyPreviewEnabled")}
        </label>
        <label className={ui.label}>
          {t("paymentInterval")}
          <select
            className={ui.input}
            value={rules.payment_interval ?? ""}
            disabled={!canUpdate}
            onChange={(e) =>
              setRules({
                ...rules,
                payment_interval: (e.target.value || null) as ReceivableRules["payment_interval"],
              })
            }
          >
            <option value="">{t("paymentIntervalOptions.none")}</option>
            <option value="monthly">{t("paymentIntervalOptions.monthly")}</option>
            <option value="quarterly">{t("paymentIntervalOptions.quarterly")}</option>
            <option value="semiannual">{t("paymentIntervalOptions.semiannual")}</option>
            <option value="annual">{t("paymentIntervalOptions.annual")}</option>
          </select>
        </label>
        <p className={ui.notice}>{t("paymentIntervalHint")}</p>
        {!canUpdate ? <p className={ui.help}>{t("readOnly")}</p> : null}
        {canUpdate ? (
          <div className={ui.formActions}>
            <button type="submit" className={ui.primary} disabled={busy}>
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
