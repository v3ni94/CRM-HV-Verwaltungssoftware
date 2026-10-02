"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

const API = "/api/bff/objektakte/previews/import";

export type PreviewRun = {
  id: string;
  status: string;
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
type State = { previews_dir: string; run: PreviewRun | null };

/** Vorschaubild-Übernahme aus objektakte (M35): Stand des letzten Laufs, Lauf starten, nach Abbruch
 *  fortsetzen. Der Start verlangt die Freigaberolle (objektakte:approve), der Server prüft sie. */
export function PreviewImportRun({ canStart }: { canStart: boolean }) {
  const t = useTranslations("ObjektakteImportRun");
  const [state, setState] = useState<State | null>(null);
  const [renderMissing, setRenderMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<State>(API);
    if (res.ok) setState(res.data);
    else setError(res.message);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const start = async (resume: boolean) => {
    setError(null);
    setInfo(null);
    const res = await bff<{ mode: string }>(API, { method: "POST", body: JSON.stringify({ render_missing: renderMissing, resume }) });
    if (!res.ok) return setError(res.message);
    setInfo(t(res.data.mode === "queued" ? "queued" : "startedInline"));
    await load();
  };
  const run = state?.run ?? null;

  return (
    <section className={ui.card} aria-label={t("previewTitle")}>
      <h2 className="text-sm font-semibold">{t("previewTitle")}</h2>
      <p className={ui.help}>{t("previewIntro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {info ? <p className={ui.help}>{info}</p> : null}
      {run ? (
        <div className="mt-2 text-sm" data-testid="preview-run">
          <span className={run.status === "failed" ? ui.badgeWarning : ui.badgeSuccess}>{run.status}</span>{" "}
          <span className={ui.help}>{formatDateTime(run.started_at)}</span>
          <p>{t("previewCounts", { processed: run.processed, total: run.total, imported: run.imported, rendered: run.rendered, missing: run.missing, skipped: run.skipped, failed: run.failed })}</p>
          {run.error ? <p className={ui.warning}>{run.error}</p> : null}
        </div>
      ) : (
        <p className={ui.help}>{t("previewNone")}</p>
      )}
      {canStart ? (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={renderMissing} onChange={(e) => setRenderMissing(e.target.checked)} />
            {t("renderMissing")}
          </label>
          <button type="button" className={ui.buttonSm} disabled={run?.status === "running"} onClick={() => void start(false)}>
            {t("previewStart")}
          </button>
          {run?.status === "failed" ? (
            <button type="button" className={ui.buttonSm} onClick={() => void start(true)}>
              {t("previewResume")}
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
