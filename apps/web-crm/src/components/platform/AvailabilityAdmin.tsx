"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Probe = { probe: string; uptime_percent: string | null; target_met: boolean | null };
type Month = {
  month: string;
  planned_downtime_seconds: number;
  probes: Probe[];
  actual_percent: string | null;
  adjusted_percent: string | null;
  target_met: boolean | null;
  target_met_adjusted: boolean | null;
};
type Out = { target_percent: string; months: Month[] };

/** Percent for display only (German decimal comma, three places); the API holds exact decimals. */
export function formatPercent(value: string | null): string {
  if (value === null) return "-";
  return `${Number(value).toLocaleString("de-DE", { minimumFractionDigits: 3, maximumFractionDigits: 3 })} %`;
}

/** GB16-02: target (99,5 percent per month) against the imported actual figures. */
export function AvailabilityAdmin() {
  const t = useTranslations("AD10");
  const [data, setData] = useState<Out | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ month: "", probe: "api", percent: "", note: "" });

  const load = useCallback(async () => {
    const res = await bff<Out>("/api/bff/platform/availability?months=12");
    if (res.ok) {
      setData(res.data);
      setError(null);
    } else setError(res.message);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const res = await bff("/api/bff/platform/availability", {
      method: "PUT",
      body: JSON.stringify({
        month: form.month,
        probe: form.probe,
        uptime_percent: form.percent.replace(",", "."),
        source_note: form.note,
      }),
    });
    if (res.ok) {
      setForm({ ...form, percent: "", note: "" });
      await load();
    } else setError(res.message);
  }

  const verdict = (v: boolean | null) => (v === null ? t("noVerdict") : v ? t("met") : t("missed"));
  const probe = (m: Month, code: string) => formatPercent(m.probes.find((p) => p.probe === code)?.uptime_percent ?? null);

  return (
    <section className={ui.pageGap} aria-labelledby="ad10-availability">
      <h2 id="ad10-availability" className="text-lg font-semibold">
        {t("availabilityTitle")}
      </h2>
      <p className={ui.notice}>
        {t("availabilityIntro", { target: formatPercent(data?.target_percent ?? "99.5") })}
      </p>
      {error ? <p className={ui.alert}>{error}</p> : null}
      {data ? (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("month")}</th>
                <th>{t("probes.api")}</th>
                <th>{t("probes.crm")}</th>
                <th>{t("probes.portal")}</th>
                <th>{t("actual")}</th>
                <th>{t("plannedMinutes")}</th>
                <th>{t("adjusted")}</th>
                <th>{t("target")}</th>
              </tr>
            </thead>
            <tbody>
              {data.months.map((m) => (
                <tr key={m.month}>
                  <td>{m.month}</td>
                  <td>{probe(m, "api")}</td>
                  <td>{probe(m, "crm")}</td>
                  <td>{probe(m, "portal")}</td>
                  <td>{formatPercent(m.actual_percent)}</td>
                  <td>{Math.round(m.planned_downtime_seconds / 60).toLocaleString("de-DE")}</td>
                  <td>{formatPercent(m.adjusted_percent)}</td>
                  <td>
                    {verdict(m.target_met)}
                    <span className={`${ui.help} block`}>{t("adjustedVerdict", { verdict: verdict(m.target_met_adjusted) })}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <p className={ui.help}>{t("adjustedHelp")}</p>
      <form onSubmit={(e) => void save(e)} className={`${ui.card} grid gap-3 sm:grid-cols-2`}>
        <h3 className="text-base font-semibold sm:col-span-2">{t("importTitle")}</h3>
        <label className="block">
          <span className={ui.label}>{t("month")}</span>
          <input className={ui.input} type="month" required value={form.month} onChange={(e) => setForm({ ...form, month: e.target.value })} />
        </label>
        <label className="block">
          <span className={ui.label}>{t("probe")}</span>
          <select className={ui.input} value={form.probe} onChange={(e) => setForm({ ...form, probe: e.target.value })}>
            {(["api", "crm", "portal"] as const).map((p) => (
              <option key={p} value={p}>
                {t(`probes.${p}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className={ui.label}>{t("percent")}</span>
          <input className={ui.input} inputMode="decimal" required placeholder="99,950" value={form.percent} onChange={(e) => setForm({ ...form, percent: e.target.value })} />
        </label>
        <label className="block">
          <span className={ui.label}>{t("note")}</span>
          <input className={ui.input} required minLength={3} maxLength={200} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          <span className={ui.help}>{t("noteHelp")}</span>
        </label>
        <div className="sm:col-span-2">
          <button type="submit" className={ui.primary}>
            {t("save")}
          </button>
        </div>
      </form>
    </section>
  );
}
