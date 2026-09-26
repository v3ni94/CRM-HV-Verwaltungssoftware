"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type SyncReport = {
  trigger?: string;
  considered?: number;
  created?: Record<string, number>;
  updated?: Record<string, number>;
  deleted_marked?: Record<string, number>;
  deletions_resolved?: Record<string, number>;
  [key: string]: unknown;
};

export type SyncState = {
  enabled: boolean;
  dump_path: string | null;
  last_source_updated_at: string | null;
  last_run_at: string | null;
  last_status: "never" | "ok" | "error";
  last_error: string | null;
  last_report: SyncReport | null;
};

export type SourceDeletion = {
  id: string;
  source_table: string;
  source_id: string;
  target_table: string;
  target_id: string | null;
  detected_at: string;
  resolved_at: string | null;
};

const SYNC = "/api/bff/objektakte/sync";

/** Route of a CRM record a deletion marker points at; tables without an own page get no link. */
export function recordHref(targetTable: string, targetId: string | null): string | null {
  if (!targetId) return null;
  if (targetTable === "property") return `/objekte/${targetId}`;
  if (targetTable === "contact") return `/kontakte/${targetId}`;
  return null;
}

function sumCounts(value: unknown): number {
  if (typeof value === "number") return value;
  if (value && typeof value === "object") {
    return Object.values(value as Record<string, unknown>).reduce<number>(
      (acc, n) => acc + (typeof n === "number" ? n : 0),
      0,
    );
  }
  return 0;
}

function countDetail(value: unknown): string {
  if (!value || typeof value !== "object") return "";
  return Object.entries(value as Record<string, unknown>)
    .filter(([, n]) => typeof n === "number" && n > 0)
    .map(([table, n]) => `${table}: ${n}`)
    .join(", ");
}

/** M35 Stufe 5: Synchronisationsstand des täglichen Differenzimports (Schalter, Exportpfad,
 * letzter Lauf mit Bericht), manueller Lauf mit oder ohne Datei und die Liste der
 * Löschmarkierungen. Spiegelt `/api/v1/objektakte/sync` und `/objektakte/sync/deletions`. */
export function SyncStatus({ initial, canEdit, canRun }: { initial: SyncState; canEdit: boolean; canRun: boolean }) {
  const t = useTranslations("Objektakte.sync");
  const [state, setState] = useState<SyncState>(initial);
  const [enabled, setEnabled] = useState(initial.enabled);
  const [dumpPath, setDumpPath] = useState(initial.dump_path ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [includeResolved, setIncludeResolved] = useState(false);
  const [deletions, setDeletions] = useState<SourceDeletion[] | null>(null);
  const [deletionsError, setDeletionsError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const res = await bff<SyncState>(SYNC);
    if (res.ok) {
      setState(res.data);
      setEnabled(res.data.enabled);
      setDumpPath(res.data.dump_path ?? "");
    } else setError(res.message);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const params = new URLSearchParams();
      if (includeResolved) params.set("include_resolved", "true");
      const res = await bff<{ items: SourceDeletion[] }>(`${SYNC}/deletions?${params.toString()}`);
      if (cancelled) return;
      if (res.ok) {
        setDeletions(res.data.items);
        setDeletionsError(null);
      } else setDeletionsError(res.message);
    })();
    return () => {
      cancelled = true;
    };
  }, [includeResolved, state.last_run_at]);

  const save = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<SyncState>(SYNC, {
      method: "PUT",
      body: JSON.stringify({ enabled, dump_path: dumpPath }),
    });
    setBusy(false);
    if (res.ok) {
      setState(res.data);
      setEnabled(res.data.enabled);
      setDumpPath(res.data.dump_path ?? "");
      setMessage(t("saved"));
    } else setError(res.message);
  };

  const runNow = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<{ mode: string }>(`${SYNC}/runs`, { method: "POST" });
    setBusy(false);
    if (res.ok) setMessage(t("queued"));
    else setError(res.message);
  };

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const form = new FormData();
    form.append("file", file);
    const res = await bff<{ mode: string }>(`${SYNC}/runs`, { method: "POST", body: form });
    setBusy(false);
    if (res.ok) {
      setFile(null);
      setMessage(t("uploaded"));
      await reload();
    } else setError(res.message);
  };

  const report = state.last_report;

  return (
    <section className={`${ui.card} flex flex-col gap-4`} aria-label={t("title")}>
      <div className="flex flex-col gap-1">
        <h2 className={ui.h2}>{t("title")}</h2>
        <p className={ui.help}>{t("intro")}</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} disabled={!canEdit || busy} onChange={(e) => setEnabled(e.target.checked)} />
          {t("enabled")}
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("dumpPath")}</span>
          <input
            className={ui.input}
            value={dumpPath}
            disabled={!canEdit || busy}
            placeholder="/data/objektakte/export.sql"
            onChange={(e) => setDumpPath(e.target.value)}
          />
        </label>
      </div>

      <div className={ui.formActions}>
        {canEdit ? (
          <button type="button" className={`${ui.primary} ${ui.actionFull}`} disabled={busy} onClick={() => void save()}>
            {t("save")}
          </button>
        ) : null}
        {canRun ? (
          <button
            type="button"
            className={`${ui.secondary} ${ui.actionFull}`}
            disabled={busy || !state.dump_path}
            onClick={() => void runNow()}
          >
            {t("runNow")}
          </button>
        ) : null}
        <button type="button" className={`${ui.secondary} ${ui.actionFull}`} disabled={busy} onClick={() => void reload()}>
          {t("reload")}
        </button>
      </div>

      {canRun ? (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("uploadLabel")}</span>
            <input type="file" accept=".sql,text/plain" disabled={busy} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <button type="button" className={ui.secondary} disabled={busy || !file} onClick={() => void upload()}>
            {t("upload")}
          </button>
        </div>
      ) : null}

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {message ? <p className={ui.success}>{message}</p> : null}

      <dl className="grid gap-2 text-sm sm:grid-cols-3" data-testid="sync-last-run">
        <div className="flex flex-col">
          <dt className={ui.label}>{t("lastRun")}</dt>
          <dd>{state.last_run_at ? formatDateTime(state.last_run_at) : t("never")}</dd>
        </div>
        <div className="flex flex-col">
          <dt className={ui.label}>{t("status")}</dt>
          <dd>
            <span
              className={
                state.last_status === "ok" ? ui.badgeSuccess : state.last_status === "error" ? ui.badgeDanger : ui.badge
              }
            >
              {t(`statusValue.${state.last_status}`)}
            </span>
          </dd>
        </div>
        <div className="flex flex-col">
          <dt className={ui.label}>{t("watermark")}</dt>
          <dd>{state.last_source_updated_at ? formatDateTime(state.last_source_updated_at) : ""}</dd>
        </div>
        {state.last_error ? (
          <div className="flex flex-col sm:col-span-3">
            <dt className={ui.label}>{t("lastError")}</dt>
            <dd className="text-danger-fg">{state.last_error}</dd>
          </div>
        ) : null}
      </dl>

      {report ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">{t("report")}</h3>
          <div className="overflow-x-auto">
            <table className={ui.table} data-testid="sync-report">
              <tbody>
                {report.trigger ? (
                  <tr>
                    <th scope="row">{t("reportTrigger")}</th>
                    <td>{report.trigger}</td>
                  </tr>
                ) : null}
                {(
                  [
                    ["considered", report.considered],
                    ["created", report.created],
                    ["updated", report.updated],
                    ["deletedMarked", report.deleted_marked],
                    ["deletionsResolved", report.deletions_resolved],
                  ] as const
                ).map(([key, value]) => (
                  <tr key={key}>
                    <th scope="row">{t(key)}</th>
                    <td>
                      {sumCounts(value)}
                      {countDetail(value) ? <span className="ml-2 text-xs text-muted">{countDetail(value)}</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold">{t("deletions")}</h3>
          <p className={ui.help}>{t("deletionsIntro")}</p>
        </div>
        <label className="flex max-w-xs flex-col gap-1">
          <span className={ui.label}>{t("deletions")}</span>
          <select className={ui.input} value={includeResolved ? "all" : "open"} onChange={(e) => setIncludeResolved(e.target.value === "all")}>
            <option value="open">{t("filterOpen")}</option>
            <option value="all">{t("filterAll")}</option>
          </select>
        </label>
        {deletionsError ? (
          <p role="alert" className={ui.alert}>
            {deletionsError}
          </p>
        ) : deletions === null ? null : deletions.length === 0 ? (
          <p className="text-sm text-muted">{t("noDeletions")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className={ui.table} data-testid="sync-deletions">
              <thead>
                <tr>
                  <th scope="col">{t("colSource")}</th>
                  <th scope="col">{t("colTarget")}</th>
                  <th scope="col">{t("colDetected")}</th>
                  <th scope="col">{t("colResolved")}</th>
                </tr>
              </thead>
              <tbody>
                {deletions.map((d) => {
                  const href = recordHref(d.target_table, d.target_id);
                  return (
                    <tr key={d.id}>
                      <td>
                        {d.source_table} #{d.source_id}
                      </td>
                      <td>
                        {href ? (
                          <Link href={href} className="underline">
                            {t("openRecord")}
                          </Link>
                        ) : (
                          <span className="text-muted">
                            {d.target_table}
                            {d.target_id ? ` ${d.target_id}` : ` (${t("noLink")})`}
                          </span>
                        )}
                      </td>
                      <td>{formatDateTime(d.detected_at)}</td>
                      <td>{d.resolved_at ? formatDateTime(d.resolved_at) : <span className={ui.badgeWarning}>{t("open")}</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
