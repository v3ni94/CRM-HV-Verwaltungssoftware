"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { groupOf, isKnownOutcome, MAX_REPORT_BYTES, parseRestoreReport, type RestoreGroup, type RestoreReport } from "@/lib/restore-report";
import { ui } from "@/lib/ui";

const ORDER: RestoreGroup[] = ["replayed", "kept", "review", "skipped"];

/** GAM-209: Restore-Protokoll auf der Betriebsseite. Zeigt je Lauf die nachgezogenen Löschungen und die
 *  bewusst erhaltenen Sperren aus dem Bericht des Wiederanwendungslaufs. Reine Anzeige im Browser:
 *  keine API, keine Speicherung, keine Freigabe (das Restore-Verfahren ist offen, AP19-02). */
export function RestoreReportView() {
  const t = useTranslations("RestoreReport");
  const [report, setReport] = useState<RestoreReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onFile(file: File | undefined) {
    setError(null);
    setReport(null);
    if (!file) return;
    if (file.size > MAX_REPORT_BYTES) return setError(t("tooLarge"));
    const parsed = parseRestoreReport(await file.text());
    if (!parsed) return setError(t("invalid"));
    setReport(parsed);
  }

  const outcomeLabel = (o: string) => (isKnownOutcome(o) ? t(`outcomes.${o}`) : t("unknownOutcome", { outcome: o }));
  const needsDecision = report ? report.results.some((r) => ["kept", "review"].includes(groupOf(r.outcome))) : false;

  return (
    <section className={`${ui.card} flex flex-col gap-3`} data-testid="restore-report">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.help}>{t("intro")}</p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("file")}</span>
        <input type="file" accept="application/json,.json" className={ui.input} onChange={(e) => void onFile(e.target.files?.[0])} />
      </label>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {report ? (
        <div className="flex flex-col gap-3">
          <p role="status" className={report.apply ? ui.success : ui.notice} data-testid="restore-mode">
            {report.apply ? t("modeApply") : t("modeDry")} {t("total", { count: report.results.length })}
          </p>
          {needsDecision ? <p className={ui.alert}>{t("reviewNeeded")}</p> : null}
          {ORDER.map((group) => {
            const rows = report.results.filter((r) => groupOf(r.outcome) === group);
            return (
              <div key={group} data-testid={`restore-group-${group}`}>
                <h3 className="text-sm font-semibold">
                  {t(`groups.${group}`)} ({rows.length})
                </h3>
                {rows.length === 0 ? (
                  <p className={ui.small}>{t("empty")}</p>
                ) : (
                  <div className={ui.tableCard}>
                    <table className="mhvp-table">
                      <thead>
                        <tr>
                          <th>{t("document")}</th>
                          <th>{t("outcome")}</th>
                          <th>{t("reason")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((r, i) => (
                          <tr key={`${r.document_id ?? "none"}-${i}`}>
                            <td className="font-mono text-xs">{r.document_id ?? ""}</td>
                            <td>{outcomeLabel(r.outcome)}</td>
                            <td>{r.reason ?? ""}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
          <button type="button" className={ui.buttonSm} onClick={() => setReport(null)}>
            {t("clear")}
          </button>
        </div>
      ) : null}
    </section>
  );
}
