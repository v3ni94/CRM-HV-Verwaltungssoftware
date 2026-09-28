"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type NoticePeriod = {
  end_on: string;
  contract_end_date: string | null;
  contract_end_covers: boolean | null;
  verify: boolean;
  note: string;
};

type Props = {
  contractId: string;
  /** Date of the termination as entered in the termination form (mirrored, editable here). */
  terminationDate: string;
  /** Contract end entered in the termination form, compared to the computed end. */
  endDate: string;
};

/** Notice period check (rule WS-01, handbook Mieterwechsel gap "Keine Prüfung der
 *  Kündigungsfrist"): the contract has no notice period field, so months and days are
 *  entered; GET /workspace/notice-period returns the end as orientation, marked "zu
 *  verifizieren". Never blocks the termination form. */
export function NoticePeriodHint({ contractId, terminationDate, endDate }: Props) {
  const t = useTranslations("NoticePeriod");
  const [months, setMonths] = useState("3");
  const [days, setDays] = useState("0");
  const [toMonthEnd, setToMonthEnd] = useState(true);
  const [result, setResult] = useState<NoticePeriod | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function compute() {
    if (!terminationDate) {
      setError(t("missingDate"));
      return;
    }
    setBusy(true);
    setError(null);
    const query = new URLSearchParams({
      termination_on: terminationDate,
      months: months || "0",
      days: days || "0",
      to_month_end: String(toMonthEnd),
      contract_id: contractId,
    });
    const res = await bff<NoticePeriod>(`/api/bff/workspace/notice-period?${query.toString()}`);
    setBusy(false);
    if (res.ok) setResult(res.data);
    else setError(res.message);
  }

  // The comparison prefers the end date typed in the form (not yet saved) over the stored one.
  const compared = endDate || result?.contract_end_date || null;
  const covers = result && compared ? compared >= result.end_on : null;

  return (
    <fieldset className={`${ui.sectionGap} rounded border border-border p-3`} data-testid="notice-period-hint">
      <legend className={ui.label}>
        {t("title")} <span className={ui.badge}>{t("verify")}</span>
      </legend>
      <p className={ui.help}>{t("intro")}</p>
      <div className="grid gap-3 sm:grid-cols-4">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("terminationOn")}</span>
          <input className={ui.input} type="date" value={terminationDate} readOnly data-testid="notice-termination" />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("months")}</span>
          <input className={ui.input} type="number" min={0} max={120} value={months} onChange={(e) => setMonths(e.target.value)} data-testid="notice-months" />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("days")}</span>
          <input className={ui.input} type="number" min={0} max={3660} value={days} onChange={(e) => setDays(e.target.value)} data-testid="notice-days" />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={toMonthEnd} onChange={(e) => setToMonthEnd(e.target.checked)} data-testid="notice-month-end" />
          {t("toMonthEnd")}
        </label>
      </div>
      <div className={ui.formActions}>
        <button type="button" className={ui.button} onClick={compute} disabled={busy} data-testid="notice-compute">
          {t("compute")}
        </button>
      </div>
      {result ? (
        <div className="flex flex-col gap-1 text-sm" data-testid="notice-result">
          <p>
            <span className="font-medium">{t("result", { date: formatDate(result.end_on) })}</span> <span className={ui.badge}>{t("verify")}</span>
          </p>
          {compared && covers !== null ? (
            <p className={covers ? ui.success : ui.notice}>{covers ? t("covers", { date: formatDate(compared) }) : t("before", { date: formatDate(compared) })}</p>
          ) : null}
          <p className={ui.help}>{t("legal")}</p>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}
