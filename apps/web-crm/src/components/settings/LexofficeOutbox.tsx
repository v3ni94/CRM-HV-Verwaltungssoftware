"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Outbound queue of the Lexware Office link (INT-LEXO-01): status filter, retry of failed
 *  rows only. Error texts are redacted by the API (no request bodies, no addresses). */
export type LexofficeOutboxRow = {
  id: string;
  config_id: string;
  kind: string;
  target_kind: string;
  target_id: string;
  status: string;
  attempts: number;
  next_attempt_at: string;
  last_status_code: number | null;
  last_error: string | null;
  sent_at: string | null;
  created_at: string;
};

const STATUSES = ["", "pending", "sent", "failed", "superseded"] as const;

export function LexofficeOutbox({ configId, canManage }: { configId: string | null; canManage: boolean }) {
  const t = useTranslations("Lexoffice");
  const [status, setStatus] = useState<string>("");
  const [rows, setRows] = useState<LexofficeOutboxRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ size: "100" });
    if (configId) params.set("config_id", configId);
    if (status) params.set("status", status);
    const res = await bff<{ items: LexofficeOutboxRow[] }>(`/api/bff/integrations/lexoffice/outbox?${params.toString()}`);
    if (res.ok) setRows(res.data.items);
    else setError(res.message);
  }, [configId, status]);

  useEffect(() => {
    void load();
  }, [load]);

  async function retry(id: string) {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<LexofficeOutboxRow>(`/api/bff/integrations/lexoffice/outbox/${id}/retry`, { method: "POST" });
    setBusy(false);
    if (res.ok) {
      setMessage(t("outbox.retried"));
      await load();
    } else setError(res.message);
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`}>
      <h2 className={ui.h2}>{t("outbox.heading")}</h2>
      <p className={ui.help}>{t("outbox.intro")}</p>
      <div>
        <label htmlFor="lx-outbox-status" className={ui.label}>
          {t("outbox.filter")}
        </label>
        <select id="lx-outbox-status" className={ui.input} value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s ? t(`outbox.status.${s}` as never) : t("outbox.all")}
            </option>
          ))}
        </select>
      </div>
      {rows.length === 0 ? <p className={ui.help}>{t("outbox.empty")}</p> : null}
      {rows.length > 0 ? (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("outbox.kind")}</th>
                <th>{t("outbox.filter")}</th>
                <th>{t("outbox.attempts")}</th>
                <th>{t("outbox.next")}</th>
                <th>{t("outbox.error")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{t(`outbox.kinds.${row.kind}` as never)}</td>
                  <td>{t(`outbox.status.${row.status}` as never)}</td>
                  <td className={ui.num}>{row.attempts}</td>
                  <td>{row.status === "pending" ? formatDateTime(row.next_attempt_at) : row.sent_at ? formatDateTime(row.sent_at) : ""}</td>
                  <td>{row.last_error ?? ""}</td>
                  <td>
                    {canManage && row.status === "failed" ? (
                      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void retry(row.id)}>
                        {t("outbox.retry")}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {message ? (
        <p role="status" className={ui.success}>
          {message}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
