"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const API = "/api/bff/objektakte/imports";

export type ImportPreview = Record<string, unknown>;
export type OcrResult = { import_run_id: string; matched: number; unmatched_keys: string[]; unmatched_count: number };

/** Importlauf der objektakte-Übernahme (M35): Export prüfen (Vorschau, ändert nichts), übernehmen,
 *  Ergebnis eines Laufs abrufen und OCR-Textcache zu einem Lauf übernehmen. */
export function ObjektakteImportRun() {
  const t = useTranslations("ObjektakteImportRun");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [previewed, setPreviewed] = useState(false);
  const [runId, setRunId] = useState("");
  const [run, setRun] = useState<Record<string, unknown> | null>(null);
  const [ocrFile, setOcrFile] = useState<File | null>(null);
  const [ocr, setOcr] = useState<OcrResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const send = async (mode: "preview" | "apply") => {
    if (!file) return;
    setError(null);
    const fd = new FormData();
    fd.set("file", file);
    const res = await bff<ImportPreview>(`${API}?mode=${mode}`, { method: "POST", body: fd });
    if (!res.ok) return setError(res.message);
    setPreview(res.data);
    setPreviewed(mode === "preview");
    if (mode === "apply" && typeof res.data.import_run_id === "string") {
      setRunId(res.data.import_run_id);
      setPreviewed(false);
    }
  };
  const loadRun = async () => {
    setError(null);
    const res = await bff<Record<string, unknown>>(`${API}/${runId.trim()}`);
    if (res.ok) setRun(res.data);
    else setError(res.message);
  };
  const sendOcr = async () => {
    if (!ocrFile) return;
    setError(null);
    const fd = new FormData();
    fd.set("file", ocrFile);
    const res = await bff<OcrResult>(`${API}/${runId.trim()}/ocr-cache`, { method: "POST", body: fd });
    if (res.ok) setOcr(res.data);
    else setError(res.message);
  };
  const validRun = /^[0-9a-f-]{36}$/i.test(runId.trim());

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <section className={ui.card} aria-label={t("runTitle")}>
        <h2 className="text-sm font-semibold">{t("runTitle")}</h2>
        <p className={ui.help}>{t("runIntro")}</p>
        <label className="mt-2 flex max-w-md flex-col gap-1">
          <span className={ui.label}>{t("dumpFile")}</span>
          <input type="file" accept=".sql,.txt" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPreviewed(false); }} />
        </label>
        <div className="mt-2 flex gap-2">
          <button type="button" className={ui.buttonSm} disabled={!file} onClick={() => void send("preview")}>
            {t("check")}
          </button>
          <button type="button" className={ui.buttonSm} disabled={!file || !previewed} onClick={() => void send("apply")}>
            {t("apply")}
          </button>
        </div>
        {!previewed && file ? <p className={ui.help}>{t("applyHint")}</p> : null}
        {preview ? (
          <pre className="mt-2 max-h-72 overflow-auto rounded-md border border-line p-2 text-xs" data-testid="import-preview">
            {JSON.stringify(preview, null, 2)}
          </pre>
        ) : null}
      </section>

      <section className={ui.card} aria-label={t("historyTitle")}>
        <h2 className="text-sm font-semibold">{t("historyTitle")}</h2>
        <label className="mt-2 flex max-w-md flex-col gap-1">
          <span className={ui.label}>{t("runId")}</span>
          <input className={ui.input} value={runId} onChange={(e) => setRunId(e.target.value)} />
        </label>
        <button type="button" className={`${ui.buttonSm} mt-2`} disabled={!validRun} onClick={() => void loadRun()}>
          {t("load")}
        </button>
        {run ? (
          <pre className="mt-2 max-h-72 overflow-auto rounded-md border border-line p-2 text-xs" data-testid="import-run">
            {JSON.stringify(run, null, 2)}
          </pre>
        ) : null}
      </section>

      <section className={ui.card} aria-label={t("ocrTitle")}>
        <h2 className="text-sm font-semibold">{t("ocrTitle")}</h2>
        <p className={ui.help}>{t("ocrIntro")}</p>
        <label className="mt-2 flex max-w-md flex-col gap-1">
          <span className={ui.label}>{t("ocrFile")}</span>
          <input type="file" accept=".zip" onChange={(e) => setOcrFile(e.target.files?.[0] ?? null)} />
        </label>
        <button type="button" className={`${ui.buttonSm} mt-2`} disabled={!ocrFile || !validRun} onClick={() => void sendOcr()}>
          {t("ocrApply")}
        </button>
        {ocr ? (
          <div className="mt-2 text-sm" data-testid="ocr-result">
            <p>{t("ocrResult", { matched: ocr.matched, unmatched: ocr.unmatched_count })}</p>
            {ocr.unmatched_keys.length ? <p className={ui.help}>{ocr.unmatched_keys.join(", ")}</p> : null}
          </div>
        ) : null}
      </section>
    </div>
  );
}
