"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Matched = { filename: string; document_id: string };
type Assigned = { document_id: string; filename: string; file_category: string | null; protocol_id: string; linked: [string, string][] };
type FilesList = { items: Assigned[]; total: number; pending_files: (string | null)[] };
type FilesResult = { matched: Matched[]; unmatched_in_zip: string[]; staged_without_file: (string | null)[] };

/** Datei Zuordnung zum U-Protokoll Import (GAF-18): ZIP des Speicherordners wird dem Importlauf
 *  zugeordnet. Zeigt zugeordnete Dateien, Dateien ohne Treffer und erwartete, aber fehlende Dateien. */
export function UprotokollFiles({ canMatch }: { canMatch: boolean }) {
  const t = useTranslations("Af20.uprotokollFiles");
  const [runId, setRunId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<FilesResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [list, setList] = useState<FilesList | null>(null);
  const [releasing, setReleasing] = useState<string | null>(null);
  const runQuery = `import_run_id=${encodeURIComponent(runId.trim())}`;
  const load = async () => {
    const res = await bff<FilesList>(`/api/bff/handover/imports/uprotokoll/files?${runQuery}`);
    if (res.ok) {
      setList({ items: res.data.items ?? [], total: res.data.total ?? 0, pending_files: res.data.pending_files ?? [] });
      setError(null);
    } else setError(res.message);
  };
  const release = async (documentId: string) => {
    setReleasing(documentId);
    setError(null);
    const res = await bff<unknown>(`/api/bff/handover/imports/uprotokoll/files/${documentId}?${runQuery}`, { method: "DELETE" });
    setReleasing(null);
    if (res.ok) await load();
    else setError(res.message);
  };
  const match = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.set("file", file);
    const res = await bff<FilesResult>(`/api/bff/handover/imports/uprotokoll/files?import_run_id=${encodeURIComponent(runId.trim())}`, { method: "POST", body: form });
    setBusy(false);
    if (res.ok) {
      setResult(res.data);
      await load();
    } else setError(res.message);
  };
  return (
    <section className={ui.card} data-testid="uprotokoll-files">
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <p className="text-xs text-muted">{t("intro")}</p>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("runId")}</span>
          <input className={ui.input} value={runId} onChange={(e) => setRunId(e.target.value)} />
        </label>
        <input type="file" accept=".zip" aria-label={t("file")} onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); }} />
        <button type="button" className={ui.secondary} disabled={!runId.trim()} onClick={() => void load()} data-testid="uprotokoll-files-load">
          {t("load")}
        </button>
        {canMatch ? (
          <button type="button" className={ui.primary} disabled={busy || !file || !runId.trim()} onClick={() => void match()}>
            {t("match")}
          </button>
        ) : null}
      </div>
      {result ? (
        <div className="mt-2 flex flex-col gap-2 text-sm" data-testid="uprotokoll-files-result">
          <div>
            <h3 className="text-xs font-semibold">{t("matched", { count: result.matched.length })}</h3>
            <ul>{result.matched.map((m) => <li key={m.document_id}>{m.filename}</li>)}</ul>
          </div>
          <div>
            <h3 className="text-xs font-semibold">{t("unmatched", { count: result.unmatched_in_zip.length })}</h3>
            <ul>{result.unmatched_in_zip.map((m) => <li key={m}>{m}</li>)}</ul>
          </div>
          <div>
            <h3 className="text-xs font-semibold">{t("missing", { count: result.staged_without_file.length })}</h3>
            <ul>{result.staged_without_file.map((m, i) => <li key={`${m}-${i}`}>{m ?? t("unnamed")}</li>)}</ul>
          </div>
        </div>
      ) : null}
      {list ? (
        <div className="mt-3 text-sm" data-testid="uprotokoll-files-list">
          <h3 className="text-xs font-semibold">{t("assigned", { count: list.total })}</h3>
          {list.items.length === 0 ? <p className="text-xs text-muted">{t("noneAssigned")}</p> : null}
          <ul>
            {list.items.map((a) => (
              <li key={a.document_id} className="flex items-center gap-2">
                <span>{a.filename}</span>
                <span className="text-xs text-muted">{a.linked.length > 0 ? t("linkedCount", { count: a.linked.length }) : t("released")}</span>
                {canMatch && a.linked.length > 0 ? (
                  <button type="button" className={ui.secondary} disabled={releasing === a.document_id} onClick={() => void release(a.document_id)}>
                    {t("release")}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
          <h3 className="mt-2 text-xs font-semibold">{t("pending", { count: list.pending_files.length })}</h3>
          <ul>{list.pending_files.map((m, i) => <li key={`${m}-${i}`}>{m ?? t("unnamed")}</li>)}</ul>
        </div>
      ) : null}
      <p className="mt-2 text-xs text-muted">{t("unlinkHint")}</p>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
