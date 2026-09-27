"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { type ImportPreview } from "@/lib/metering";
import { ui } from "@/lib/ui";

/** CSV import and export of assignments (section 6): template, preview with validation report
 *  and duplicate protection, apply only by an explicit second step, export with numbers as text. */
export function AssignmentsCsv({ canUpdate, onApplied }: { canUpdate: boolean; onApplied?: () => void }) {
  const t = useTranslations("Metering.csv");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [applied, setApplied] = useState<ImportPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(mode: "preview" | "apply") {
    if (!file) return;
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.append("file", file);
    const res = await bff<ImportPreview>(`/api/bff/metering/assignments-import/${mode}`, { method: "POST", body });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    if (mode === "preview") {
      setPreview(res.data);
      setApplied(null);
    } else {
      setApplied(res.data);
      setPreview(null);
      onApplied?.();
    }
  }

  const report = applied ?? preview;

  return (
    <section className={ui.card} data-testid="metering-csv">
      <h3 className={ui.subtitle}>{t("title")}</h3>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <a className={ui.buttonSm} href="/api/bff/metering/assignments-import/template" download>
          {t("template")}
        </a>
        <a className={ui.buttonSm} href="/api/bff/metering/assignments-export" download>
          {t("export")}
        </a>
      </div>
      {canUpdate ? (
        <div className="mt-3 flex flex-col gap-2">
          <input
            type="file"
            accept=".csv,text/csv"
            aria-label={t("file")}
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setPreview(null);
              setApplied(null);
            }}
          />
          <div className="flex flex-wrap gap-2">
            <button type="button" className={ui.button} disabled={!file || busy} onClick={() => run("preview")} data-testid="csv-preview">
              {t("preview")}
            </button>
            <button type="button" className={ui.primary} disabled={!preview || preview.ok_count === 0 || busy} onClick={() => run("apply")} data-testid="csv-apply">
              {t("apply")}
            </button>
          </div>
          <p className={ui.help}>{t("applyHint")}</p>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
      {report ? (
        <div className="mt-3" data-testid="csv-report">
          <p className="text-sm">
            {applied ? t("appliedSummary", { count: applied.created_ids.length }) : t("previewSummary", { ok: report.ok_count, errors: report.error_count, duplicates: report.duplicate_count })}
          </p>
          <div className="mt-2 overflow-x-auto">
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("line")}</th>
                  <th>{t("status")}</th>
                  <th>{t("values")}</th>
                  <th>{t("messages")}</th>
                </tr>
              </thead>
              <tbody>
                {report.rows.map((r) => (
                  <tr key={r.line} data-testid={`csv-row-${r.line}`}>
                    <td className="tabular-nums">{r.line}</td>
                    <td>
                      <StatusPill variant={r.status === "ok" ? "success" : r.status === "duplicate" ? "warning" : "danger"} label={t(`rowStatus.${r.status}`)} />
                    </td>
                    <td className="font-mono text-xs">
                      {Object.entries(r.values)
                        .map(([k, v]) => `${k}=${v}`)
                        .join(" ")}
                    </td>
                    <td className="text-xs">{r.messages.join("; ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}
