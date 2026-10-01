"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { formatPercent } from "./AvailabilityAdmin";

type SelfFigure = {
  probe: string;
  counted_percent: string | null;
  coverage_percent: string;
};
type Month = {
  month: string;
  self_probes: SelfFigure[];
  self_gross_percent: string | null;
  self_net_percent: string | null;
  self_counted_percent: string | null;
  self_failed_in_maintenance_minutes: number | null;
  self_coverage_percent: string | null;
  self_target_met: boolean | null;
  self_final: boolean | null;
};
type Availability = { maintenance_counts_as_downtime: boolean; min_coverage_percent: string; months: Month[] };
type LiveProbe = {
  probe: string;
  configured: boolean;
  host: string | null;
  last_checked_at: string | null;
  last_ok: boolean | null;
  last_status_code: number | null;
  last_latency_ms: number | null;
  last_error_class: string | null;
  checks_24h: number;
  ok_24h: number;
  percent_24h: string | null;
};
type Failure = { probe: string; slot: string; status_code: number | null; error_class: string | null };
type Live = { probes: LiveProbe[]; recent_failures: Failure[]; retention_days: number };

const PROBES = ["api", "crm", "portal"] as const;
const ERROR_CLASSES = ["timeout", "connect_error", "http_status", "http_error", "error"];
const fmt = (iso: string) => new Date(iso).toLocaleString("de-DE", { timeZone: "Europe/Berlin" });

/** Percent for the coverage column (one place), "-" without a figure. */
export function formatCoverage(value: string | null): string {
  if (value === null) return "-";
  return `${Number(value).toLocaleString("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`;
}

/** AE35 (GB16-02, AD10-02): own availability measurement, live status, months and the switch. */
export function AvailabilitySelfMeasurement() {
  const t = useTranslations("AE35");
  const [live, setLive] = useState<Live | null>(null);
  const [data, setData] = useState<Availability | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [l, a] = await Promise.all([
      bff<Live>("/api/bff/platform/availability/live"),
      bff<Availability>("/api/bff/platform/availability?months=12"),
    ]);
    if (l.ok) setLive(l.data);
    if (a.ok) setData(a.data);
    setError(!l.ok ? l.message : !a.ok ? a.message : null);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function toggle(next: boolean) {
    const res = await bff("/api/bff/platform/availability/settings", {
      method: "PUT",
      body: JSON.stringify({ maintenance_counts_as_downtime: next }),
    });
    if (res.ok) await load();
    else setError(res.message);
  }

  const verdict = (v: boolean | null) => (v === null ? t("noVerdict") : v ? t("met") : t("missed"));
  const errorText = (code: string | null) => (code === null ? "-" : ERROR_CLASSES.includes(code) ? t(`errors.${code}`) : code);
  const counts = data?.maintenance_counts_as_downtime ?? false;
  const months = (data?.months ?? []).filter((m) => m.self_probes.length > 0);
  const anyConfigured = live?.probes.some((p) => p.configured) ?? false;

  return (
    <section className={ui.pageGap} aria-labelledby="ae35-self">
      <h2 id="ae35-self" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className={ui.notice}>{t("intro")}</p>
      {error ? <p className={ui.alert}>{error}</p> : null}
      {live && !anyConfigured ? <p className={ui.help}>{t("notConfigured")}</p> : null}

      {live ? (
        <>
          <div className={ui.tableScroll}>
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("probe")}</th>
                  <th>{t("host")}</th>
                  <th>{t("lastCheck")}</th>
                  <th>{t("result")}</th>
                  <th>{t("latency")}</th>
                  <th>{t("last24h")}</th>
                </tr>
              </thead>
              <tbody>
                {live.probes.map((p) => (
                  <tr key={p.probe}>
                    <td>{t(`probes.${p.probe}`)}</td>
                    <td>{p.configured ? p.host : t("off")}</td>
                    <td>{p.last_checked_at ? fmt(p.last_checked_at) : t("noCheckYet")}</td>
                    <td>
                      {p.last_ok === null ? (
                        "-"
                      ) : p.last_ok ? (
                        <span className={ui.badgeSuccess}>{t("reachable")}</span>
                      ) : (
                        <span className={ui.badgeDanger}>
                          {p.last_status_code ?? errorText(p.last_error_class)}
                        </span>
                      )}
                    </td>
                    <td>{p.last_latency_ms === null ? "-" : `${p.last_latency_ms.toLocaleString("de-DE")} ms`}</td>
                    <td>{p.checks_24h === 0 ? "-" : `${formatPercent(p.percent_24h)} (${p.ok_24h.toLocaleString("de-DE")} / ${p.checks_24h.toLocaleString("de-DE")})`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {live.recent_failures.length > 0 ? (
            <details className={ui.card}>
              <summary className="cursor-pointer text-sm font-semibold">{t("failuresTitle")}</summary>
              <ul className="mt-2 space-y-1 text-sm">
                {live.recent_failures.map((f) => (
                  <li key={`${f.probe}-${f.slot}`}>
                    {fmt(f.slot)}: {t(`probes.${f.probe}`)}, {f.status_code ?? errorText(f.error_class)}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
          <p className={ui.help}>{t("retention", { days: live.retention_days })}</p>
        </>
      ) : null}

      <div className={`${ui.card} space-y-2`}>
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-1" checked={counts} onChange={(e) => void toggle(e.target.checked)} />
          <span>
            <span className={ui.label}>{t("switchLabel")}</span>
            <span className={`${ui.help} block`}>{t("switchHelp")}</span>
          </span>
        </label>
      </div>

      <h3 className="text-base font-semibold">{t("monthsTitle")}</h3>
      {data && months.length === 0 ? <p className={ui.help}>{t("noMonths")}</p> : null}
      {months.length > 0 ? (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("month")}</th>
                {PROBES.map((p) => (
                  <th key={p}>{t(`probes.${p}`)}</th>
                ))}
                <th>{t("rated", { basis: counts ? t("basisAll") : t("basisNet") })}</th>
                <th>{t("gross")}</th>
                <th>{t("net")}</th>
                <th>{t("maintenanceMinutes")}</th>
                <th>{t("coverage")}</th>
                <th>{t("target")}</th>
              </tr>
            </thead>
            <tbody>
              {months.map((m) => (
                <tr key={m.month}>
                  <td>
                    {m.month}
                    <span className={`${ui.help} block`}>{m.self_final ? t("final") : t("provisional")}</span>
                  </td>
                  {PROBES.map((p) => (
                    <td key={p}>{formatPercent(m.self_probes.find((f) => f.probe === p)?.counted_percent ?? null)}</td>
                  ))}
                  <td>{formatPercent(m.self_counted_percent)}</td>
                  <td>{formatPercent(m.self_gross_percent)}</td>
                  <td>{formatPercent(m.self_net_percent)}</td>
                  <td>{m.self_failed_in_maintenance_minutes === null ? "-" : m.self_failed_in_maintenance_minutes.toLocaleString("de-DE")}</td>
                  <td>{formatCoverage(m.self_coverage_percent)}</td>
                  <td>{verdict(m.self_target_met)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <p className={ui.help}>{t("verdictHelp", { min: formatCoverage(data?.min_coverage_percent ?? "95") })}</p>
    </section>
  );
}
