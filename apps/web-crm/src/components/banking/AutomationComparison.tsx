"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import { formatRate } from "./MatchingMetricsCard";

export type ComparisonRow = {
  decision_id: string;
  case_kind: string;
  outcome: string;
  decided_at: string | null;
};
export type ComparisonData = {
  outcomes: string[];
  totals: Record<string, number>;
  by_case_kind: Record<string, Record<string, number>>;
  compared_bookings: number;
  match_rate: string | null;
  rows: ComparisonRow[];
  note: string;
};

/** Vergleich Automatik gegen manuelle Buchung (`GET /banking/automation/comparison`, 7.4):
 *  Bericht je Zeitraum, bucht nichts und ist kein Sicherheitsnachweis. */
export function AutomationComparison() {
  const t = useTranslations("Bank.kpi");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [data, setData] = useState<ComparisonData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams();
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    setLoading(true);
    bff<ComparisonData>(`/api/bff/banking/automation/comparison?${params.toString()}`).then((r) => {
      if (cancelled) return;
      setLoading(false);
      if (r.ok) {
        setData(r.data);
        setError(null);
      } else {
        setData(null);
        setError(r.message);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [from, to]);

  return (
    <section className={ui.card} data-testid="automation-comparison" aria-labelledby="kpi-comparison-title">
      <h2 id="kpi-comparison-title" className={ui.h2}>
        {t("comparisonTitle")}
      </h2>
      <p className="mt-1 text-sm text-muted">{t("comparisonIntro")}</p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="flex flex-col text-xs text-muted">
          {t("from")}
          <input type="date" className={ui.input} value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="flex flex-col text-xs text-muted">
          {t("to")}
          <input type="date" className={ui.input} value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
      </div>
      {error ? (
        <p role="alert" className={`${ui.alert} mt-3`}>
          {error}
        </p>
      ) : null}
      {loading && !data ? (
        <p role="status" className="mt-3 text-sm text-muted">
          {t("loading")}
        </p>
      ) : null}
      {data ? (
        <>
          <p className="mt-3 text-sm" data-testid="comparison-summary">
            {t("summary", { compared: data.compared_bookings, rate: formatRate(data.match_rate, t("noRate")) })}
          </p>
          <div className={ui.tableScroll}>
            <table className={ui.table} data-testid="comparison-table">
              <thead>
                <tr>
                  <th>{t("caseKind")}</th>
                  {data.outcomes.map((o) => (
                    <th key={o}>{t(`outcome.${o}`)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{t("total")}</td>
                  {data.outcomes.map((o) => (
                    <td key={o} className={ui.num}>
                      {data.totals[o] ?? 0}
                    </td>
                  ))}
                </tr>
                {Object.entries(data.by_case_kind).map(([kind, counts]) => (
                  <tr key={kind}>
                    <td>{kind}</td>
                    {data.outcomes.map((o) => (
                      <td key={o} className={ui.num}>
                        {counts[o] ?? 0}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.rows.length > 0 ? (
            <p className="mt-2 text-xs text-muted">
              {t("lastDecision", { date: formatDate(data.rows[0]?.decided_at ?? null) })}
            </p>
          ) : null}
          <p className="mt-2 text-xs text-muted">{t("note")}</p>
        </>
      ) : null}
    </section>
  );
}
