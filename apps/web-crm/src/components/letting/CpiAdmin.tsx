"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

type CpiRow = { series: string; month: string; value: string; source: string; data_as_of: string; released: boolean };

const SERIES = /^[A-Za-z0-9_.-]{1,40}$/;

/** Verbraucherpreisindex pflegen (AO03, GAL-301): zweistufig. Schritt 1 importiert Werte per CSV
 *  (Quelle und Stand Pflicht), sie bleiben ungeprüft und wirken nirgends. Schritt 2 gibt Werte einer
 *  Reihe bis zu einem Monat ausdrücklich frei; erst freigegebene Werte nutzen Indexklauseln und
 *  Erhöhungsvorschläge. Nur für Plattformadministratoren (die API prüft es). Die Seite öffnet kein Gate. */
export function CpiAdmin() {
  const t = useTranslations("PlatformCpi");
  const [series, setSeries] = useState("");
  const [source, setSource] = useState("");
  const [asOf, setAsOf] = useState("");
  const [csv, setCsv] = useState("");
  const [rows, setRows] = useState<CpiRow[] | null>(null);
  const [upTo, setUpTo] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { busy, guard } = useBusy();

  const seriesOk = SERIES.test(series);
  const unreleased = (rows ?? []).filter((r) => !r.released);

  async function loadRows(name: string) {
    const res = await bff<CpiRow[]>(`/api/bff/letting/consumer-price-index?series=${encodeURIComponent(name)}`);
    if (res.ok) setRows(res.data);
    else {
      setRows(null);
      setError(res.message);
    }
  }

  const show = guard(async () => {
    setError(null);
    setMessage(null);
    if (seriesOk) await loadRows(series);
  });

  const importCsv = guard(async () => {
    setError(null);
    setMessage(null);
    const res = await bff<{ created: number; updated: number; unchanged: number }>("/api/bff/platform/consumer-price-index/import", {
      method: "POST",
      body: JSON.stringify({ series, source: source.trim(), data_as_of: asOf, csv }),
    });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setMessage(t("imported", res.data));
    setCsv("");
    await loadRows(series);
  });

  const release = guard(async () => {
    setError(null);
    setMessage(null);
    const res = await bff<{ released: number }>("/api/bff/platform/consumer-price-index/release", {
      method: "POST",
      body: JSON.stringify({ series, up_to: `${upTo}-01` }),
    });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setMessage(t("released", { count: res.data.released }));
    setConfirmed(false);
    await loadRows(series);
  });

  async function readFile(file: File | undefined) {
    if (file) setCsv(await file.text());
  }

  return (
    <div className="flex flex-col gap-4" data-testid="cpi-admin">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className={ui.notice}>
          {message}
        </p>
      ) : null}
      <section className={ui.card}>
        <h2 className="mb-2 font-medium">{t("importTitle")}</h2>
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("series")}</span>
            <input className={ui.input} value={series} maxLength={40} onChange={(e) => setSeries(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("source")}</span>
            <input className={ui.input} value={source} maxLength={500} onChange={(e) => setSource(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("dataAsOf")}</span>
            <input className={ui.input} type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("file")}</span>
            <input type="file" accept=".csv,.txt,text/csv,text/plain" onChange={(e) => void readFile(e.target.files?.[0])} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("csv")}</span>
            <textarea className={`${ui.input} font-mono`} rows={6} value={csv} onChange={(e) => setCsv(e.target.value)} />
          </label>
          <p className="text-xs text-muted">{t("csvHint")}</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={ui.buttonSm} disabled={busy || !seriesOk || source.trim().length < 3 || !asOf || !csv.trim()} onClick={() => void importCsv()}>
              {t("import")}
            </button>
            <button type="button" className={ui.buttonSm} disabled={busy || !seriesOk} onClick={() => void show()}>
              {t("show")}
            </button>
          </div>
        </div>
      </section>
      <section className={ui.card}>
        <h2 className="mb-2 font-medium">{t("valuesTitle")}</h2>
        {rows === null ? (
          <p className="text-sm text-muted">{t("noSelection")}</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted">{t("empty")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" data-testid="cpi-values">
              <thead>
                <tr>
                  <th className="pr-2">{t("month")}</th>
                  <th className="pr-2">{t("value")}</th>
                  <th className="pr-2">{t("source")}</th>
                  <th className="pr-2">{t("dataAsOf")}</th>
                  <th>{t("status")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.month} className="border-t">
                    <td className="pr-2">{r.month.slice(0, 7)}</td>
                    <td className="pr-2">{r.value.replace(".", ",")}</td>
                    <td className="pr-2">{r.source}</td>
                    <td className="pr-2">{formatDate(r.data_as_of)}</td>
                    <td>
                      <span className={r.released ? ui.badgeSuccess : ui.badgeWarning}>{r.released ? t("releasedBadge") : t("draftBadge")}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className={ui.card}>
        <h2 className="mb-2 font-medium">{t("releaseTitle")}</h2>
        <p className="mb-2 text-sm text-muted">{t("releaseHint")}</p>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("upTo")}</span>
            <input className={ui.input} type="month" value={upTo} onChange={(e) => { setUpTo(e.target.value); setConfirmed(false); }} />
          </label>
          {upTo ? (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
              {t("confirm", { count: unreleased.filter((r) => r.month.slice(0, 7) <= upTo).length, series, upTo })}
            </label>
          ) : null}
          <button type="button" className={ui.buttonSm} disabled={busy || !seriesOk || !upTo || !confirmed} onClick={() => void release()}>
            {t("release")}
          </button>
        </div>
      </section>
    </div>
  );
}
