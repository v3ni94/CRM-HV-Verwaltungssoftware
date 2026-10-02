"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { Pagination } from "@/components/ui/Pagination";
import { useConfirm } from "@/components/ui/ConfirmSheet";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type ImportRunRow = {
  id: string;
  status: string;
  created_at: string;
  created_total: number;
  updated_total: number;
  skipped_duplicates_total: number;
  considered_total: number;
  deleted_marked: number;
  cache_documents: number;
};

export type PreviewRun = {
  status: "running" | "done" | "failed";
  trigger: string;
  total: number;
  processed: number;
  imported: number;
  rendered: number;
  missing: number;
  skipped: number;
  failed: number;
  started_at: string;
  finished_at: string | null;
  error: string | null;
};

type PreviewState = { previews_dir: string | null; run: PreviewRun | null };

const RUNS = "/api/bff/objektakte/import-runs";
const PREVIEWS = "/api/bff/objektakte/previews/import";
const PAGE_SIZE = 10;

/** GAG-12: Verlauf der objektakte-Importläufe (Status, Datum, Zahlen), OCR-Cache je Lauf
 * leeren (mit Bestätigung, nur Texte, keine Dokumente) und Vorschaubild-Übernahme starten.
 * Spiegelt `GET /objektakte/import-runs`, `DELETE /objektakte/import-runs/{id}/ocr-cache`
 * sowie `GET/POST /objektakte/previews/import`. */
export function ImportRunHistory({ canClear, canStartPreviews }: { canClear: boolean; canStartPreviews: boolean }) {
  const t = useTranslations("Objektakte.importRuns");
  const { confirm, confirmSheet } = useConfirm();
  const [rows, setRows] = useState<ImportRunRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [previews, setPreviews] = useState<PreviewState | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [renderMissing, setRenderMissing] = useState(false);

  const load = useCallback(async (target: number) => {
    const res = await bff<ImportRunRow[]>(`${RUNS}?page=${target}&page_size=${PAGE_SIZE}`);
    if (res.ok) {
      setRows(res.data);
      setTotal(res.totalCount ?? res.data.length);
      setError(null);
    } else setError(res.message);
  }, []);

  const loadPreviews = useCallback(async () => {
    const res = await bff<PreviewState>(PREVIEWS);
    if (res.ok) {
      setPreviews(res.data);
      setPreviewError(null);
    } else setPreviewError(res.message);
  }, []);

  useEffect(() => {
    void load(page);
  }, [load, page]);
  useEffect(() => {
    void loadPreviews();
  }, [loadPreviews]);

  const clearCache = async (run: ImportRunRow) => {
    const ok = await confirm({
      title: t("clearTitle"),
      text: t("clearText", { count: run.cache_documents }),
      confirmLabel: t("clearConfirm"),
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<{ cleared: number }>(`${RUNS}/${run.id}/ocr-cache`, { method: "DELETE" });
    setBusy(false);
    if (res.ok) {
      setMessage(t("cleared", { count: res.data.cleared }));
      await load(page);
    } else setError(res.message);
  };

  const startPreviews = async () => {
    setBusy(true);
    setPreviewError(null);
    setMessage(null);
    const res = await bff<{ mode: string }>(PREVIEWS, {
      method: "POST",
      body: JSON.stringify({ render_missing: renderMissing, resume: true }),
    });
    setBusy(false);
    if (res.ok) {
      setMessage(t("previewStarted"));
      await loadPreviews();
    } else setPreviewError(res.message);
  };

  const run = previews?.run ?? null;

  return (
    <section className={`${ui.card} flex flex-col gap-4`} aria-label={t("title")}>
      <div className="flex flex-col gap-1">
        <h2 className={ui.h2}>{t("title")}</h2>
        <p className={ui.help}>{t("intro")}</p>
      </div>

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {message ? <p className={ui.success}>{message}</p> : null}

      {rows === null ? null : rows.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className={ui.table} data-testid="import-runs">
            <thead>
              <tr>
                <th scope="col">{t("colDate")}</th>
                <th scope="col">{t("colStatus")}</th>
                <th scope="col">{t("colCreated")}</th>
                <th scope="col">{t("colUpdated")}</th>
                <th scope="col">{t("colSkipped")}</th>
                <th scope="col">{t("colCache")}</th>
                <th scope="col">
                  <span className="sr-only">{t("colActions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} data-testid={`import-run-${r.id}`}>
                  <td>{formatDateTime(r.created_at)}</td>
                  <td>
                    <span className={ui.badge}>{r.status}</span>
                  </td>
                  <td>{r.created_total}</td>
                  <td>{r.updated_total}</td>
                  <td>{r.skipped_duplicates_total}</td>
                  <td>{r.cache_documents}</td>
                  <td>
                    {canClear ? (
                      <button
                        type="button"
                        className={ui.secondary}
                        disabled={busy || r.cache_documents === 0}
                        data-testid={`clear-cache-${r.id}`}
                        onClick={() => void clearCache(r)}
                      >
                        {t("clearCache")}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={total}
        shown={rows?.length ?? 0}
        control={{ kind: "button", onChange: setPage, disabled: busy }}
        labels={{
          label: t("pagination"),
          range: (from, to, all) => t("range", { from, to, total: all }),
          page: (p, pages) => t("pageOf", { page: p, pages }),
          prev: t("prev"),
          next: t("next"),
        }}
        testId="import-runs-pagination"
      />

      <div className="flex flex-col gap-2 border-t pt-4">
        <h3 className="text-sm font-semibold">{t("previewTitle")}</h3>
        <p className={ui.help}>{t("previewIntro")}</p>
        {previewError ? (
          <p role="alert" className={ui.alert}>
            {previewError}
          </p>
        ) : null}
        {run ? (
          <dl className="grid gap-2 text-sm sm:grid-cols-4" data-testid="preview-run">
            <div className="flex flex-col">
              <dt className={ui.label}>{t("previewStatus")}</dt>
              <dd>{t(`previewStatusValue.${run.status}`)}</dd>
            </div>
            <div className="flex flex-col">
              <dt className={ui.label}>{t("previewStartedAt")}</dt>
              <dd>{formatDateTime(run.started_at)}</dd>
            </div>
            <div className="flex flex-col">
              <dt className={ui.label}>{t("previewProgress")}</dt>
              <dd>
                {run.processed} / {run.total}
              </dd>
            </div>
            <div className="flex flex-col">
              <dt className={ui.label}>{t("previewImported")}</dt>
              <dd>
                {run.imported} ({t("previewMissing", { count: run.missing })}, {t("previewFailed", { count: run.failed })})
              </dd>
            </div>
            {run.error ? <dd className="text-danger-fg sm:col-span-4">{run.error}</dd> : null}
          </dl>
        ) : previews ? (
          <p className="text-sm text-muted">{t("previewNone")}</p>
        ) : null}
        {canStartPreviews ? (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={renderMissing} disabled={busy} onChange={(e) => setRenderMissing(e.target.checked)} />
              {t("previewRenderMissing")}
            </label>
            <button
              type="button"
              className={ui.primary}
              disabled={busy || run?.status === "running"}
              data-testid="start-previews"
              onClick={() => void startPreviews()}
            >
              {t("previewStart")}
            </button>
            <button type="button" className={ui.secondary} disabled={busy} onClick={() => void loadPreviews()}>
              {t("previewReload")}
            </button>
          </div>
        ) : null}
      </div>
      {confirmSheet}
    </section>
  );
}
