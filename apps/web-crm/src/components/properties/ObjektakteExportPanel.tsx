"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type ExportRun = {
  id: string;
  status: "queued" | "running" | "done" | "failed";
  document_id: string | null;
  counts: Record<string, number>;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  download_count: number;
};
type Listing = { items: ExportRun[]; personal_data_note: string; can_start: boolean };

/** Objektakte export for the successor manager (handbook Verwalterwechsel, Abgabe): the
 *  operator confirms the export and the personal data note, the API queues the background
 *  job, the ZIP is filed as a document and downloaded here (every download is an audit
 *  event). Needs properties:update and documents:read, checked server side again. */
export function ObjektakteExportPanel({ propertyId, canExport }: { propertyId: string; canExport: boolean }) {
  const t = useTranslations("ObjektakteExport");
  const [listing, setListing] = useState<Listing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [started, setStarted] = useState(false);
  const base = `/api/bff/properties/${propertyId}/objektakte-export`;

  const load = useCallback(async () => {
    const res = await bff<Listing>(base);
    if (res.ok) setListing(res.data);
    else setError(res.message);
  }, [base]);

  useEffect(() => {
    void load();
  }, [load]);

  async function start() {
    setBusy(true);
    setError(null);
    const res = await bff<ExportRun>(base, {
      method: "POST",
      body: JSON.stringify({ confirm: true, personal_data_acknowledged: acknowledged, note: note.trim() || null }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setConfirming(false);
    setStarted(true);
    await load();
  }

  const pending = listing?.items.some((r) => r.status === "queued" || r.status === "running") ?? false;

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="objektakte-export-title" data-testid="objektakte-export">
      <h2 id="objektakte-export-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className={ui.help}>{t("intro")}</p>
      {!canExport ? <p className="text-xs text-muted">{t("readOnly")}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {canExport && !confirming ? (
        <div className={ui.formActions}>
          <button type="button" className={ui.primary} onClick={() => setConfirming(true)} disabled={busy || pending} data-testid="export-start">
            {t("start")}
          </button>
          <button type="button" className={ui.buttonSm} onClick={() => void load()}>
            {t("refresh")}
          </button>
        </div>
      ) : null}
      {confirming ? (
        <div className="flex flex-col gap-2 rounded-md border border-border p-3" role="dialog" aria-labelledby="export-confirm-title">
          <p id="export-confirm-title" className="font-medium">
            {t("confirmTitle")}
          </p>
          <p className={ui.notice} data-testid="export-note">
            {listing?.personal_data_note}
          </p>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("note")}</span>
            <input className={ui.input} value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} />
          </label>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} data-testid="export-acknowledge" />
            <span>{t("acknowledge")}</span>
          </label>
          <div className={ui.formActions}>
            <button type="button" className={ui.primary} onClick={() => void start()} disabled={busy || !acknowledged} data-testid="export-confirm">
              {t("confirm")}
            </button>
            <button type="button" className={ui.secondary} onClick={() => setConfirming(false)}>
              {t("cancel")}
            </button>
          </div>
        </div>
      ) : null}
      {started ? <p className={ui.success}>{t("started")}</p> : null}
      <div className="flex flex-col gap-2">
        <p className={ui.label}>{t("runs")}</p>
        {listing === null ? null : listing.items.length === 0 ? (
          <p className="text-sm text-muted">{t("none")}</p>
        ) : (
          <ul className="flex flex-col gap-2 text-sm" data-testid="export-runs">
            {listing.items.map((run) => (
              <li key={run.id} className="flex flex-wrap items-center gap-2">
                <span className={run.status === "done" ? ui.badgeSuccess : run.status === "failed" ? ui.badgeDanger : ui.badgeWarning}>{t(`status.${run.status}`)}</span>
                <span className="text-muted">{formatDateTime(run.created_at)}</span>
                {run.status === "done" ? (
                  <>
                    <span className="text-xs text-muted">
                      {t("counts", {
                        documents: run.counts.documents ?? 0,
                        units: run.counts.units ?? 0,
                        owners: run.counts.owners ?? 0,
                        tenants: run.counts.tenants ?? 0,
                        open_items: run.counts.open_items ?? 0,
                      })}
                    </span>
                    {canExport ? (
                      <a className={ui.buttonSm} href={`${base}/${run.id}/download`} download data-testid={`export-download-${run.id}`}>
                        {t("download")}
                      </a>
                    ) : null}
                    <span className="text-xs text-muted">{t("downloads", { count: run.download_count })}</span>
                  </>
                ) : null}
                {run.status === "failed" && run.error ? <span className="text-xs text-danger-fg">{run.error}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
