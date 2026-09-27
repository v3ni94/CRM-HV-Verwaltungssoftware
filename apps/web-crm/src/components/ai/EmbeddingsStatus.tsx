"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import type { EmbeddingStatus } from "@/lib/ai";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Embedding index of the tenant (M7-03): counters from `GET /ai/embeddings/status` and the
 *  rebuild (`POST /ai/embeddings/reindex`, incremental or `full`), permission
 *  `tenant_settings:update` (the page itself requires it). The job runs in the background;
 *  the status is refreshed on demand. */
export function EmbeddingsStatus({ initial }: { initial: EmbeddingStatus | null }) {
  const t = useTranslations("AiSettings.embeddings");
  const [status, setStatus] = useState<EmbeddingStatus | null>(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setBusy(true);
    setError(null);
    const res = await bff<EmbeddingStatus>("/api/bff/ai/embeddings/status");
    setBusy(false);
    if (res.ok) setStatus(res.data);
    else setError(res.message);
  }

  async function reindex(full: boolean) {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<EmbeddingStatus>("/api/bff/ai/embeddings/reindex", {
      method: "POST",
      body: JSON.stringify({ full }),
    });
    setBusy(false);
    if (res.ok) {
      setStatus(res.data);
      setMessage(res.data.queued ? t("queued") : t("done"));
    } else setError(res.message);
  }

  const runStatus = (value: string | null | undefined) =>
    value === "succeeded" || value === "failed" || value === "running" ? t(`runStatus.${value}`) : (value ?? "");

  return (
    <section className={ui.card} aria-labelledby="ai-embeddings-title">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="ai-embeddings-title" className={ui.h2}>
            {t("title")}
          </h2>
          <span
            className={`rounded-md px-2 py-0.5 text-xs font-medium ${status?.enabled ? "bg-success-bg text-success-fg" : "bg-surface text-muted"}`}
            data-testid="ai-embeddings-model"
          >
            {status?.enabled ? `${t("model")}: ${status.model ?? ""}` : t("disabled")}
          </span>
        </div>
        <p className={ui.help}>{t("description")}</p>
        {status && !status.enabled && status.reason ? <p className="text-xs text-warning-fg">{status.reason}</p> : null}
        {status ? (
          <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2" data-testid="ai-embeddings-counts">
            <dt className="text-muted">{t("documents")}</dt>
            <dd>{t("embedded", { embedded: status.documents_embedded, total: status.documents_total, pending: status.documents_pending })}</dd>
            <dt className="text-muted">{t("knowledge")}</dt>
            <dd>{t("embedded", { embedded: status.knowledge_embedded, total: status.knowledge_total, pending: status.knowledge_pending })}</dd>
            <dt className="text-muted">{t("chunks")}</dt>
            <dd>{status.chunks}</dd>
            <dt className="text-muted">{t("lastRun")}</dt>
            <dd data-testid="ai-embeddings-last-run">
              {status.last_run_at ? `${formatDateTime(status.last_run_at)} (${runStatus(status.last_run_status)})` : t("noRun")}
              {status.last_run_error ? <span className="block text-xs text-danger-fg">{status.last_run_error}</span> : null}
            </dd>
          </dl>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className={ui.primary} disabled={busy || !status?.enabled} onClick={() => void reindex(false)}>
            {t("reindex")}
          </button>
          <button type="button" className={ui.secondary} disabled={busy || !status?.enabled} onClick={() => void reindex(true)}>
            {t("reindexFull")}
          </button>
          <button type="button" className={ui.secondary} disabled={busy} onClick={() => void refresh()}>
            {t("refresh")}
          </button>
        </div>
        <p className={ui.help}>{t("fullHint")}</p>
        {message ? <span className="text-xs text-success-fg">{message}</span> : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
