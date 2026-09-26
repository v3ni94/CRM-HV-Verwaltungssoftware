"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type MatchingMetrics = {
  period_from: string | null;
  period_to: string | null;
  transactions: number;
  incoming: number;
  auto_matched: number;
  manual_booked: number;
  open: number;
  ignored: number;
  coverage: string | null;
  auto_reversed: number;
  auto_corrected: number;
  auto_cancelled: number;
  error_rate: string | null;
  note: string;
};

function isoMonthStart(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

function isoToday(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** "0.4000" → "40,0 %"; null → placeholder (no base, no figure). */
export function formatRate(value: string | null, placeholder: string): string {
  if (value === null || value === undefined || value === "") return placeholder;
  const n = Number(value);
  if (!Number.isFinite(n)) return placeholder;
  return `${(n * 100).toLocaleString("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`;
}

/** Kennzahlenkarte des Bankabgleichs: Abdeckungsgrad und Fehlerquote getrennt, je Zeitraum (A45).
 *  Betriebskennzahlen aus vorhandenen Daten; keine Freigabe der Automatik (7.4). */
export function MatchingMetricsCard({ initialFrom, initialTo }: { initialFrom?: string; initialTo?: string } = {}) {
  const t = useTranslations("Bank.metrics");
  const now = new Date();
  const [from, setFrom] = useState(initialFrom ?? isoMonthStart(now));
  const [to, setTo] = useState(initialTo ?? isoToday(now));
  const [data, setData] = useState<MatchingMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams();
    if (from) params.set("from", from);
    if (to) params.set("to", to);
    setLoading(true);
    bff<MatchingMetrics>(`/api/bff/banking/matching-metrics?${params.toString()}`).then((r) => {
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

  const none = t("noBase");
  return (
    <section className={ui.card} data-testid="matching-metrics">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
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
        <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <dt className="text-xs text-muted">{t("coverage")}</dt>
            <dd className="text-2xl font-semibold text-fg" data-testid="metric-coverage">
              {formatRate(data.coverage, none)}
            </dd>
            <dd className="text-xs text-muted">{t("coverageBase", { auto: data.auto_matched, total: data.transactions })}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{t("errorRate")}</dt>
            <dd className="text-2xl font-semibold text-fg" data-testid="metric-error-rate">
              {formatRate(data.error_rate, none)}
            </dd>
            <dd className="text-xs text-muted">
              {t("errorBase", { reversed: data.auto_reversed, auto: data.auto_matched, corrected: data.auto_corrected, cancelled: data.auto_cancelled })}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{t("manual")}</dt>
            <dd className="text-2xl font-semibold text-fg">{data.manual_booked}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{t("open")}</dt>
            <dd className="text-2xl font-semibold text-fg">{data.open}</dd>
            <dd className="text-xs text-muted">{t("ignored", { count: data.ignored })}</dd>
          </div>
        </dl>
      ) : null}
      {data ? (
        <p className="mt-3 text-xs text-muted">
          {t("period", { from: formatDate(data.period_from), to: formatDate(data.period_to) })} {t("note")}
        </p>
      ) : null}
    </section>
  );
}
