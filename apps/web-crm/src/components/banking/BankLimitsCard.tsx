"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { BankAccountSelect } from "./BankAccountSelect";

type Limits = {
  single_order_limit: string | null;
  daily_limit: string | null;
  source_status: string;
  verification_of_payee: string;
  lead_times: {
    frst_days: number | null;
    rcur_days: number | null;
    pre_notification_days: number | null;
    note: string;
  };
};
const MONEY = /^\d+([.,]\d{1,2})?$/;

/** M15-04/M15-06: Banklimits und Einreichungsfristen je Auftraggeberkonto als Betreibereingabe
 * nach Bankvereinbarung (kein gesetzlicher Standardwert). Hinweis zur Empfängerprüfung (VoP). */
export function BankLimitsCard() {
  const t = useTranslations("BankLimits");
  const [accountId, setAccountId] = useState<string | null>(null);
  const [limits, setLimits] = useState<Limits | null>(null);
  const [f, setF] = useState({ single: "", daily: "", frst: "", rcur: "", pre: "" });
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accountId) return;
    setLimits(null);
    setMessage(null);
    void bff<Limits>(`/api/bff/accounting/payment-runs/bank-limits/${accountId}`).then((res) => {
      if (!res.ok) return setError(res.message);
      setError(null);
      setLimits(res.data);
      setF({
        single: res.data.single_order_limit ?? "",
        daily: res.data.daily_limit ?? "",
        frst: res.data.lead_times.frst_days?.toString() ?? "",
        rcur: res.data.lead_times.rcur_days?.toString() ?? "",
        pre: res.data.lead_times.pre_notification_days?.toString() ?? "",
      });
    });
  }, [accountId]);

  const moneyOk = (v: string) => v.trim() === "" || MONEY.test(v.trim());
  const intOk = (v: string) => v.trim() === "" || /^\d{1,3}$/.test(v.trim());
  const valid = moneyOk(f.single) && moneyOk(f.daily) && intOk(f.frst) && intOk(f.rcur) && intOk(f.pre);
  const money = (v: string) => (v.trim() === "" ? null : v.trim().replace(",", "."));
  const int = (v: string) => (v.trim() === "" ? null : Number.parseInt(v.trim(), 10));
  const save = async () => {
    if (!accountId) return;
    setError(null);
    setMessage(null);
    const res = await bff<Limits>(`/api/bff/accounting/payment-runs/bank-limits/${accountId}`, {
      method: "PUT",
      body: JSON.stringify({
        single_order_limit: money(f.single),
        daily_limit: money(f.daily),
        dd_lead_days_frst: int(f.frst),
        dd_lead_days_rcur: int(f.rcur),
        pre_notification_days: int(f.pre),
      }),
    });
    if (!res.ok) return setError(res.message);
    setLimits(res.data);
    setMessage(t("saved"));
  };
  const field = (k: keyof typeof f, label: string, inputMode: "decimal" | "numeric") => (
    <label className="flex flex-col gap-1">
      <span className={ui.label}>{label}</span>
      <input className={ui.input} inputMode={inputMode} value={f[k]} onChange={(e) => setF((v) => ({ ...v, [k]: e.target.value }))} />
    </label>
  );
  return (
    <section className={ui.card} data-testid="bank-limits">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.notice}>{t("notice")}</p>
      <BankAccountSelect value={accountId} onChange={(a) => setAccountId(a?.id ?? null)} label={t("account")} />
      {limits ? (
        <div className="flex flex-col gap-2">
          <div className="grid gap-2 sm:grid-cols-5">
            {field("single", t("singleLimit"), "decimal")}
            {field("daily", t("dailyLimit"), "decimal")}
            {field("frst", t("leadFrst"), "numeric")}
            {field("rcur", t("leadRcur"), "numeric")}
            {field("pre", t("leadPre"), "numeric")}
          </div>
          <p className={ui.help}>{t("sourceStatus", { status: limits.source_status })}</p>
          <p className={ui.help} data-testid="vop-note">{limits.verification_of_payee}</p>
          <p className={ui.help}>{limits.lead_times.note}</p>
          <button type="button" className={ui.button} onClick={save} disabled={!valid}>
            {t("save")}
          </button>
        </div>
      ) : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {message ? <p role="status" className={ui.success}>{message}</p> : null}
    </section>
  );
}
