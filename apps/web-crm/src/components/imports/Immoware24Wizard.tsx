"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ImportUndoButton } from "@/components/ai/ImportUndoButton";
import type { DocumentOut } from "@/lib/ai";
import { bff } from "@/lib/bff";
import {
  API,
  REPORT_TYPES,
  STAGED_ONLY,
  type ImportField,
  type ImportMapping,
  type ImportSource,
  type Reconciliation,
  type ReportType,
  type RunReport,
} from "@/lib/immoware";
import { ui } from "@/lib/ui";

import { ReconciliationView, RunReportView, ValidationReport } from "./ImportReports";
import { MappingStep } from "./MappingStep";

type Props = { fields: Record<string, ImportField[]>; mappings: ImportMapping[]; canUndo: boolean };
type Step = "type" | "upload" | "mapping" | "validate" | "done";

export function Immoware24Wizard({ fields, mappings: initialMappings, canUndo }: Props) {
  const t = useTranslations("Immoware24");
  const [step, setStep] = useState<Step>("type");
  const [reportType, setReportType] = useState<ReportType>("properties");
  const [file, setFile] = useState<File | null>(null);
  const [sheet, setSheet] = useState("");
  const [headerRow, setHeaderRow] = useState("1");
  const [source, setSource] = useState<ImportSource | null>(null);
  const [mappings, setMappings] = useState(initialMappings);
  const [mapping, setMapping] = useState<ImportMapping | null>(null);
  const [testRun, setTestRun] = useState<RunReport | null>(null);
  const [applied, setApplied] = useState<RunReport | null>(null);
  const [recon, setRecon] = useState<Reconciliation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fail = (message: string) => {
    setBusy(false);
    setError(message);
  };

  const upload = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!file) return setError(t("fileRequired"));
    const row = Number(headerRow);
    if (!Number.isInteger(row) || row < 1 || row > 50) return setError(t("headerRowInvalid"));
    setBusy(true);
    const form = new FormData();
    form.set("file", file);
    form.set("title", file.name);
    const doc = await bff<DocumentOut>("/api/bff/documents", { method: "POST", body: form });
    if (!doc.ok) return fail(doc.message);
    const res = await bff<ImportSource>(`${API}/files`, {
      method: "POST",
      body: JSON.stringify({ document_id: doc.data.id, report_type: reportType, sheet: sheet.trim() || null, header_row: row }),
    });
    if (!res.ok) return fail(res.message);
    setBusy(false);
    setSource(res.data);
    setStep("mapping");
  };

  const validate = async (m: ImportMapping) => {
    if (!source) return;
    setMapping(m);
    if (!mappings.some((x) => x.id === m.id)) setMappings((list) => [...list.map((x) => (x.name === m.name && x.report_type === m.report_type ? { ...x, active: false } : x)), m]);
    setError(null);
    setBusy(true);
    const res = await bff<ImportSource>(`${API}/files/${source.id}/validate`, { method: "POST", body: JSON.stringify({ mapping_id: m.id }) });
    if (!res.ok) return fail(res.message);
    setBusy(false);
    setSource(res.data);
    setTestRun(null);
    setStep("validate");
  };

  const runTest = async () => {
    if (!source) return;
    setError(null);
    setBusy(true);
    const res = await bff<RunReport>(`${API}/files/${source.id}/test-run`, { method: "POST" });
    if (!res.ok) return fail(res.message);
    setBusy(false);
    setTestRun(res.data);
  };

  const apply = async () => {
    if (!source || !window.confirm(t("applyConfirm"))) return;
    setError(null);
    setBusy(true);
    const res = await bff<ImportSource>(`${API}/files/${source.id}/apply`, { method: "POST" });
    if (!res.ok) return fail(res.message);
    setSource(res.data);
    setApplied((res.data.report.apply as RunReport | undefined) ?? null);
    const rec = await bff<Reconciliation>(`${API}/files/${source.id}/reconciliation`);
    setBusy(false);
    if (rec.ok) setRecon(rec.data);
    else setError(rec.message);
    setStep("done");
  };

  const restart = () => {
    setStep("type");
    setFile(null);
    setSource(null);
    setMapping(null);
    setTestRun(null);
    setApplied(null);
    setRecon(null);
    setError(null);
  };

  const validation = (source?.report.validation as Record<string, number> | undefined) ?? {};

  return (
    <div className="flex flex-col gap-6">
      <ol className="flex flex-wrap gap-3 text-xs text-muted" aria-label={t("stepsLabel")}>
        {(["type", "upload", "mapping", "validate", "done"] as Step[]).map((s, i) => (
          <li key={s} aria-current={s === step ? "step" : undefined} className={s === step ? "font-semibold text-fg" : ""}>
            {i + 1}. {t(`step.${s}`)}
          </li>
        ))}
      </ol>

      {step === "type" ? (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold">{t("typeTitle")}</h2>
          <p className={ui.notice}>{t("orderHint")}</p>
          <fieldset className="flex flex-col gap-2">
            <legend className="sr-only">{t("typeTitle")}</legend>
            {REPORT_TYPES.map((r) => (
              <label key={r} className="flex items-center gap-2 text-sm">
                <input type="radio" name="report_type" value={r} checked={reportType === r} onChange={() => setReportType(r)} />
                {t(`report.${r}`)}
                {STAGED_ONLY.includes(r) ? <span className="text-xs text-muted">{t("stagedOnlyBadge")}</span> : null}
              </label>
            ))}
          </fieldset>
          {STAGED_ONLY.includes(reportType) ? <p className={ui.notice}>{t("stagedOnlyHint")}</p> : null}
          <div>
            <button type="button" className={ui.primary} onClick={() => setStep("upload")}>
              {t("next")}
            </button>
          </div>
        </section>
      ) : null}

      {step === "upload" ? (
        <form className="flex max-w-lg flex-col gap-3" onSubmit={upload}>
          <h2 className="text-lg font-semibold">{t("uploadTitle", { report: t(`report.${reportType}`) })}</h2>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("file")}</span>
            <input
              type="file"
              accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("sheet")}</span>
            <input className={ui.input} value={sheet} maxLength={100} onChange={(e) => setSheet(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("headerRow")}</span>
            <input className={ui.input} type="number" min={1} max={50} value={headerRow} onChange={(e) => setHeaderRow(e.target.value)} />
          </label>
          <div className="flex gap-2">
            <button type="button" className={ui.button} onClick={() => setStep("type")}>
              {t("back")}
            </button>
            <button type="submit" className={ui.primary} disabled={busy}>
              {t("uploadSubmit")}
            </button>
          </div>
        </form>
      ) : null}

      {source && step !== "type" && step !== "upload" ? (
        <p className="text-sm text-muted">
          {t("sourceInfo", { report: t(`report.${source.report_type}`), rows: source.row_count, headers: source.headers.length })}
        </p>
      ) : null}

      {step === "mapping" && source ? (
        <MappingStep source={source} fields={fields[source.report_type] ?? []} mappings={mappings} onMapping={validate} />
      ) : null}

      {step === "validate" && source ? (
        <section className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold">{t("validationTitle")}</h2>
          {mapping ? <p className="text-sm text-muted">{t("templateOption", { name: mapping.name, version: mapping.version })}</p> : null}
          <ValidationReport sourceId={source.id} counts={validation} />
          <div className="flex flex-wrap gap-2">
            <button type="button" className={ui.button} onClick={() => setStep("mapping")}>
              {t("backToMapping")}
            </button>
            <button type="button" className={ui.button} onClick={runTest} disabled={busy}>
              {t("testRun")}
            </button>
            <button type="button" className={ui.primary} onClick={apply} disabled={busy}>
              {t("apply")}
            </button>
          </div>
          {testRun ? (
            <section className={ui.card} aria-labelledby="testrun-title">
              <h3 id="testrun-title" className="text-base font-semibold">
                {t("testRunTitle")}
              </h3>
              <p className={`${ui.notice} my-2`} data-testid="test-run-notice">
                {t("testRunNotice")}
              </p>
              <RunReportView report={testRun} testId="test-run-report" />
            </section>
          ) : null}
        </section>
      ) : null}

      {step === "done" && source ? (
        <section className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold">{t("applyTitle")}</h2>
          {applied ? <RunReportView report={applied} testId="apply-report" /> : null}
          {source.import_run_id ? (
            <div className="flex flex-wrap items-center gap-3">
              <Link href={`/importe/${source.import_run_id}`} className="text-sm font-medium hover:underline">
                {t("runLink")}
              </Link>
              {canUndo ? <ImportUndoButton id={source.import_run_id} /> : null}
            </div>
          ) : null}
          <h3 className="text-base font-semibold">{t("reconTitle")}</h3>
          {recon ? <ReconciliationView data={recon} /> : null}
          <div>
            <button type="button" className={ui.button} onClick={restart}>
              {t("restart")}
            </button>
          </div>
        </section>
      ) : null}

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
