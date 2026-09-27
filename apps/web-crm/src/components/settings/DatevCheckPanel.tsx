"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Shapes of /api/v1/accounting/datev (M18-01 self check). Local types, the generated
 *  api-client is regenerated centrally. */
export type DatevExportRun = {
  id: string;
  ledger_id: string;
  period_from: string;
  period_to: string;
  rows: number;
  sha256: string;
  note: string | null;
  created_at: string;
  checked_at: string | null;
  check_status: string | null;
  has_content: boolean;
};

export type CheckFinding = {
  rule: string;
  title: string;
  source: "belegt" | "zu_pruefen";
  severity: "error" | "warning" | "info";
  line: number | null;
  field: string | null;
  value: string | null;
  message: string;
};

export type CheckReport = {
  status: "formal_ok" | "mit_hinweisen" | "fehlerhaft";
  errors: number;
  warnings: number;
  infos: number;
  booking_rows: number;
  header_fields: number;
  columns: string[];
  rules: { id: string; title: string; source: string; reference: string; checked: boolean }[];
  findings: CheckFinding[];
  disclaimer: string;
};

export type CheckOut = {
  export_id: string | null;
  checked_at: string | null;
  report: CheckReport;
  text: string;
};

const BASE = "/api/bff/accounting/datev";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
}

export function DatevCheckPanel({ initial, canCheck }: { initial: DatevExportRun[]; canCheck: boolean }) {
  const t = useTranslations("DatevCheck");
  const [runs, setRuns] = useState<DatevExportRun[]>(initial);
  const [current, setCurrent] = useState<CheckOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [adhoc, setAdhoc] = useState("");

  async function reload() {
    const res = await bff<DatevExportRun[]>(`${BASE}/exports`);
    if (res.ok) setRuns(res.data);
  }

  async function check(run: DatevExportRun) {
    setBusy(true);
    setError(null);
    const res = await bff<CheckOut>(`${BASE}/exports/${run.id}/check`, { method: "POST" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setCurrent(res.data);
    await reload();
  }

  async function show(run: DatevExportRun) {
    setError(null);
    const res = await bff<CheckOut>(`${BASE}/exports/${run.id}/check`);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setCurrent(res.data);
  }

  async function readFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setAdhoc(await file.text());
  }

  async function checkAdhoc(event: React.FormEvent) {
    event.preventDefault();
    if (!adhoc.trim()) return;
    setBusy(true);
    setError(null);
    const res = await bff<CheckOut>(`${BASE}/check-file`, { method: "POST", body: JSON.stringify({ content: adhoc }) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setCurrent(res.data);
  }

  const report = current?.report ?? null;

  return (
    <section className={ui.sectionGap} aria-labelledby="datev-check-title">
      <div className={ui.card}>
        <h2 id="datev-check-title" className={ui.h2}>
          {t("title")}
        </h2>
        <p className={`${ui.small} mt-1`}>{t("intro")}</p>
        {!canCheck ? <p className={`${ui.notice} mt-2`}>{t("readOnly")}</p> : null}
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}

      <div className={ui.card}>
        <h3 className={ui.h3}>{t("exports")}</h3>
        {runs.length === 0 ? (
          <p className={`${ui.small} mt-2`}>{t("noExports")}</p>
        ) : (
          <div className="mt-2 overflow-x-auto">
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("colCreated")}</th>
                  <th>{t("colPeriod")}</th>
                  <th className="num">{t("colRows")}</th>
                  <th>{t("colStatus")}</th>
                  <th>{t("colActions")}</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td>{formatDate(run.created_at)}</td>
                    <td>
                      {formatDate(run.period_from)} bis {formatDate(run.period_to)}
                    </td>
                    <td className={`num ${ui.num}`}>{run.rows}</td>
                    <td>
                      {run.check_status
                        ? t(`status.${run.check_status}` as "status.formal_ok")
                        : run.has_content
                          ? t("unchecked")
                          : t("noContent")}
                    </td>
                    <td className="flex flex-wrap gap-1">
                      {canCheck && run.has_content ? (
                        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => check(run)}>
                          {t("check")}
                        </button>
                      ) : null}
                      {run.check_status ? (
                        <button type="button" className={ui.buttonSm} onClick={() => show(run)}>
                          {t("showReport")}
                        </button>
                      ) : null}
                      {run.has_content ? (
                        <a className={ui.buttonSm} href={`${BASE}/exports/${run.id}/download`} download>
                          {t("download")}
                        </a>
                      ) : null}
                      {run.check_status ? (
                        <a className={ui.buttonSm} href={`${BASE}/exports/${run.id}/check?format=text`} download>
                          {t("reportText")}
                        </a>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {report ? (
        <div className={ui.card} data-testid="datev-check-report">
          <h3 className={ui.h3}>
            {t("report")}: {t(`status.${report.status}`)}
          </h3>
          <p className={`${ui.small} mt-1`}>
            {t("summary", { rows: report.booking_rows, errors: report.errors, warnings: report.warnings })}
          </p>
          {report.findings.length === 0 ? (
            <p className={`${ui.success} mt-2`}>{t("noFindings")}</p>
          ) : (
            <div className="mt-2 overflow-x-auto">
              <table className={ui.table}>
                <thead>
                  <tr>
                    <th>{t("colRule")}</th>
                    <th>{t("colSeverity")}</th>
                    <th>{t("colSource")}</th>
                    <th className="num">{t("colLine")}</th>
                    <th>{t("colField")}</th>
                    <th>{t("colMessage")}</th>
                  </tr>
                </thead>
                <tbody>
                  {report.findings.map((f, i) => (
                    <tr key={`${f.rule}-${f.line ?? 0}-${i}`}>
                      <td className={ui.mono}>{f.rule}</td>
                      <td>{t(`severity.${f.severity}`)}</td>
                      <td>{t(`source.${f.source}`)}</td>
                      <td className={`num ${ui.num}`}>{f.line ?? ""}</td>
                      <td>{f.field ?? ""}</td>
                      <td>{f.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <details className="mt-3">
            <summary className={ui.small}>{t("rules")}</summary>
            <ul className={`${ui.small} mt-1 list-disc pl-5`}>
              {report.rules.map((r) => (
                <li key={r.id}>
                  <span className={ui.mono}>{r.id}</span> {r.title} ({t(`source.${r.source}` as "source.belegt")})
                </li>
              ))}
            </ul>
          </details>
          <p className={`${ui.notice} mt-3`}>{report.disclaimer}</p>
        </div>
      ) : null}

      <div className={ui.card}>
        <h3 className={ui.h3}>{t("sampleTitle")}</h3>
        <p className={`${ui.small} mt-1`}>{t("sampleHelp")}</p>
        <a className={`${ui.button} mt-2`} href={`${BASE}/sample-batch`} download>
          {t("sampleDownload")}
        </a>
      </div>

      <form className={ui.card} onSubmit={checkAdhoc}>
        <h3 className={ui.h3}>{t("adhocTitle")}</h3>
        <p className={`${ui.small} mt-1`}>{t("adhocHelp")}</p>
        <input type="file" accept=".csv,.txt" className="mt-2 text-sm" onChange={readFile} aria-label={t("adhocTitle")} />
        <label className={`${ui.label} mt-2`} htmlFor="datev-adhoc">
          {t("adhocContent")}
        </label>
        <textarea id="datev-adhoc" className={`${ui.input} ${ui.mono} min-h-32`} value={adhoc} onChange={(e) => setAdhoc(e.target.value)} />
        <div className={`${ui.formActions} mt-2`}>
          <button type="submit" className={ui.primary} disabled={busy || !adhoc.trim()}>
            {t("adhocRun")}
          </button>
        </div>
      </form>
    </section>
  );
}
