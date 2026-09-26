"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDateTime, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

const API = "/api/bff/imports/reconciliation-reports";
const METRICS = ["kontosaldo", "debitoren_op", "kreditoren_op", "ruecklage", "bankstand", "zahlungen"] as const;

export type ReportLine = {
  property_number: string;
  metric: string;
  key: string | null;
  source: string | null;
  platform: string | null;
  difference: string | null;
  deviates: boolean;
  hint: string | null;
};

export type ReportSummary = {
  id: string;
  created_at: string;
  as_of: string | null;
  trigger: string | null;
  totals: Record<string, number>;
  sources: { id: string; report_type: string; row_count: number }[];
};

export type Report = ReportSummary & {
  counts: Record<string, number>;
  warnings: string[];
  properties: { number: string; name: string | null; on_platform: boolean; compared: number; deviations: number }[];
  lines: ReportLine[];
};

/** Reconciliation reports of the parallel operation (A68): list, manual run, detail with
 * differences per property and metric, CSV download. Read only, nothing is posted. */
export function ReconciliationReports({ canCreate }: { canCreate: boolean }) {
  const t = useTranslations("ReconciliationReports");
  const [reports, setReports] = useState<ReportSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [onlyDeviations, setOnlyDeviations] = useState(true);
  const [asOf, setAsOf] = useState("");

  const load = useCallback(async () => {
    const res = await bff<ReportSummary[]>(API);
    if (res.ok) setReports(res.data);
    else {
      setReports([]);
      setError(res.message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const open = async (id: string) => {
    setError(null);
    const res = await bff<Report>(`${API}/${id}`);
    if (res.ok) setSelected(res.data);
    else setError(res.message);
  };

  const create = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<Report>(API, { method: "POST", body: JSON.stringify(asOf ? { as_of: asOf } : {}) });
    setBusy(false);
    if (res.ok) {
      setSelected(res.data);
      await load();
    } else setError(res.message);
  };

  const metricLabel = (metric: string) => ((METRICS as readonly string[]).includes(metric) ? t(`metric.${metric}`) : metric);
  const triggerLabel = (trigger: string | null) => (trigger === "beat" ? t("triggerBeat") : t("triggerManual"));
  const visible = selected ? selected.lines.filter((line) => !onlyDeviations || line.deviates) : [];

  return (
    <div className={ui.sectionGap}>
      <p className={ui.notice}>{t("readOnlyNote")}</p>
      {canCreate ? (
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void create();
          }}
        >
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("asOf")}</span>
            <input type="date" className={ui.input} value={asOf} onChange={(event) => setAsOf(event.target.value)} />
          </label>
          <button type="submit" className={ui.primary} disabled={busy} data-testid="reconciliation-create">
            {busy ? t("creating") : t("create")}
          </button>
          <span className={ui.help}>{t("asOfHelp")}</span>
        </form>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {reports === null ? (
        <p className="text-sm text-muted">{t("loading")}</p>
      ) : reports.length === 0 ? (
        <p className="text-sm text-muted" data-testid="reconciliation-empty">
          {t("empty")}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className={ui.table} data-testid="reconciliation-list">
            <thead>
              <tr>
                <th>{t("colCreated")}</th>
                <th>{t("colAsOf")}</th>
                <th>{t("colTrigger")}</th>
                <th>{t("colProperties")}</th>
                <th>{t("colDeviations")}</th>
                <th>{t("colActions")}</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((report) => (
                <tr key={report.id} data-testid="reconciliation-row">
                  <td>
                    <button type="button" className="font-medium hover:underline" onClick={() => void open(report.id)}>
                      {formatDateTime(report.created_at)}
                    </button>
                  </td>
                  <td>{formatDate(report.as_of)}</td>
                  <td>{triggerLabel(report.trigger)}</td>
                  <td>{report.totals.properties ?? 0}</td>
                  <td>{report.totals.deviations ?? 0}</td>
                  <td>
                    <a className="text-sm font-medium hover:underline" href={`${API}/${report.id}/csv`} download>
                      {t("downloadCsv")}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selected ? (
        <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("detailTitle")} data-testid="reconciliation-detail">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-sm font-semibold">
              {t("detailTitle")} {formatDate(selected.as_of)}
            </h2>
            <span className={ui.badge}>{triggerLabel(selected.trigger)}</span>
            <a className="text-sm font-medium hover:underline" href={`${API}/${selected.id}/csv`} download>
              {t("downloadCsv")}
            </a>
          </div>
          <dl className="flex flex-wrap gap-6 text-sm" data-testid="reconciliation-totals">
            {(["properties", "compared", "deviations", "missing_on_platform"] as const).map((key) => (
              <div key={key} className="flex flex-col">
                <dt className="text-xs text-muted">{t(`totals.${key}`)}</dt>
                <dd className="font-semibold">{selected.totals[key] ?? 0}</dd>
              </div>
            ))}
          </dl>
          {selected.warnings.length > 0 ? (
            <div className={ui.notice} data-testid="reconciliation-warnings">
              <p className="font-medium">{t("warnings", { count: selected.warnings.length })}</p>
              <ul className="mt-1 list-disc pl-4">
                {selected.warnings.slice(0, 20).map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={onlyDeviations} onChange={(event) => setOnlyDeviations(event.target.checked)} />
            {t("onlyDeviations")}
          </label>
          {visible.length === 0 ? (
            <p className="text-sm text-muted" data-testid="reconciliation-no-lines">
              {t("noLines")}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className={ui.table} data-testid="reconciliation-lines">
                <thead>
                  <tr>
                    <th>{t("colProperty")}</th>
                    <th>{t("colMetric")}</th>
                    <th>{t("colKey")}</th>
                    <th className="text-right">{t("colSource")}</th>
                    <th className="text-right">{t("colPlatform")}</th>
                    <th className="text-right">{t("colDifference")}</th>
                    <th>{t("colHint")}</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((line) => (
                    <tr key={`${line.property_number}-${line.metric}-${line.key ?? ""}`} className={line.deviates ? "font-medium" : undefined}>
                      <td>{line.property_number}</td>
                      <td>{metricLabel(line.metric)}</td>
                      <td>{line.key ?? ""}</td>
                      <td className="text-right tabular-nums">{line.source === null ? t("missing") : formatEur(line.source)}</td>
                      <td className="text-right tabular-nums">{line.platform === null ? t("missing") : formatEur(line.platform)}</td>
                      <td className="text-right tabular-nums">{line.difference === null ? "" : formatEur(line.difference)}</td>
                      <td className="text-muted">{line.hint ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
