"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Schadenbearbeiter am Ticket (INT-SDT-01): hand the ticket over, then send chosen comments
 *  and documents. Internal notes are never sent by default; only what is entered or selected
 *  here leaves the platform. The actions only queue the exchange; the result shows here. */
export type SchadenstoolItem = {
  id: string;
  kind: "comment" | "attachment";
  direction: "outbound" | "inbound";
  local_id: string;
  remote_id: string | null;
  author_name: string | null;
  state: string;
  last_error: string | null;
  created_at: string;
};
export type SchadenstoolLink = {
  enabled: boolean;
  linked: boolean;
  link_id?: string | null;
  remote_id?: string | null;
  remote_status?: string | null;
  remote_status_label?: string | null;
  sync_status?: string | null;
  last_synced_at?: string | null;
  last_error?: string | null;
  token_invalid?: boolean;
  pending?: number;
  failed?: number;
  items?: SchadenstoolItem[];
  documents?: { id: string; filename: string; sent: boolean }[];
};

export function SchadenstoolPanel({ ticketId, canUpdate }: { ticketId: string; canUpdate: boolean }) {
  const t = useTranslations("Schadenstool");
  const [data, setData] = useState<SchadenstoolLink | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [reporter, setReporter] = useState("");
  const [damageDate, setDamageDate] = useState("");
  const [damageType, setDamageType] = useState("");
  const [damageLocation, setDamageLocation] = useState("");
  const [comment, setComment] = useState("");
  const [documentId, setDocumentId] = useState("");

  const base = `/api/bff/integrations/schadenstool/tickets/${ticketId}`;
  const load = useCallback(async () => {
    const res = await bff<SchadenstoolLink>(base);
    if (res.ok) setData(res.data);
  }, [base]);

  useEffect(() => {
    void load();
  }, [load]);

  async function post(path: string, body: object, done: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<{ queued: boolean }>(`${base}/${path}`, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return false;
    }
    setMessage(done);
    await load();
    return true;
  }

  if (data === null || (!data.enabled && !data.linked)) return null;

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="sdt-panel-title">
      <h2 id="sdt-panel-title" className={ui.h2}>
        {t("panelTitle")}
      </h2>
      {data.token_invalid ? (
        <p role="alert" className={ui.alert}>
          {t("tokenInvalid")}
        </p>
      ) : null}
      {!data.linked ? (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void post(
              "handover",
              {
                ...(reporter.trim() ? { reporter: reporter.trim() } : {}),
                ...(damageDate ? { damage_date: damageDate } : {}),
                ...(damageType.trim() ? { damage_type: damageType.trim() } : {}),
                ...(damageLocation.trim() ? { damage_location: damageLocation.trim() } : {}),
              },
              t("handoverQueued"),
            );
          }}
        >
          <p className={ui.help}>{t("handoverIntro")}</p>
          <label htmlFor="sdt-reporter" className={ui.label}>
            {t("reporter")}
          </label>
          <input id="sdt-reporter" className={ui.input} value={reporter} maxLength={200} disabled={!canUpdate} onChange={(e) => setReporter(e.target.value)} />
          <label htmlFor="sdt-damage-date" className={ui.label}>
            {t("damageDate")}
          </label>
          <input id="sdt-damage-date" type="date" className={ui.input} value={damageDate} disabled={!canUpdate} onChange={(e) => setDamageDate(e.target.value)} />
          <label htmlFor="sdt-damage-type" className={ui.label}>
            {t("damageType")}
          </label>
          <input id="sdt-damage-type" className={ui.input} value={damageType} maxLength={100} disabled={!canUpdate} onChange={(e) => setDamageType(e.target.value)} />
          <label htmlFor="sdt-damage-location" className={ui.label}>
            {t("damageLocation")}
          </label>
          <input id="sdt-damage-location" className={ui.input} value={damageLocation} maxLength={300} disabled={!canUpdate} onChange={(e) => setDamageLocation(e.target.value)} />
          {canUpdate ? (
            <div className={ui.formActions}>
              <button type="submit" className={ui.primary} disabled={busy}>
                {t("handover")}
              </button>
            </div>
          ) : null}
        </form>
      ) : (
        <>
          <dl className="grid grid-cols-1 gap-1 text-sm sm:grid-cols-2">
            <dt className="text-muted">{t("remoteStatus")}</dt>
            <dd>{data.remote_status_label ?? t("unknown")}</dd>
            <dt className="text-muted">{t("syncStatus")}</dt>
            <dd>{t(`sync.${data.sync_status ?? "unknown"}` as "sync.linked")}</dd>
            <dt className="text-muted">{t("lastSynced")}</dt>
            <dd>{data.last_synced_at ? formatDateTime(data.last_synced_at) : t("never")}</dd>
            <dt className="text-muted">{t("queue")}</dt>
            <dd>{t("queueCounts", { pending: data.pending ?? 0, failed: data.failed ?? 0 })}</dd>
          </dl>
          {data.last_error ? (
            <p role="alert" className={ui.alert}>
              {data.last_error}
            </p>
          ) : null}
          {(data.items ?? []).length > 0 ? (
            <ul className="flex flex-col gap-1 text-sm">
              {(data.items ?? []).map((item) => (
                <li key={item.id}>
                  {item.direction === "inbound"
                    ? t("itemInbound", { kind: t(`kind.${item.kind}`), author: item.author_name ?? t("adjuster") })
                    : t("itemOutbound", { kind: t(`kind.${item.kind}`), state: t(`state.${item.state}` as "state.sent") })}{" "}
                  <span className="text-muted">{formatDateTime(item.created_at)}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {canUpdate ? (
            <>
              <form
                className="flex flex-col gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void post("comments", { body: comment.trim() }, t("commentQueued")).then((ok) => ok && setComment(""));
                }}
              >
                <label htmlFor="sdt-comment" className={ui.label}>
                  {t("comment")}
                </label>
                <textarea id="sdt-comment" className={ui.input} rows={3} value={comment} maxLength={20000} onChange={(e) => setComment(e.target.value)} />
                <p className={ui.help}>{t("commentHint")}</p>
                <div className={ui.formActions}>
                  <button type="submit" className={ui.primary} disabled={busy || !comment.trim()}>
                    {t("sendComment")}
                  </button>
                </div>
              </form>
              {(data.documents ?? []).length > 0 ? (
                <form
                  className="flex flex-col gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void post("attachments", { document_id: documentId }, t("attachmentQueued"));
                  }}
                >
                  <label htmlFor="sdt-document" className={ui.label}>
                    {t("document")}
                  </label>
                  <select id="sdt-document" className={ui.input} value={documentId} onChange={(e) => setDocumentId(e.target.value)}>
                    <option value="">{t("chooseDocument")}</option>
                    {(data.documents ?? []).map((d) => (
                      <option key={d.id} value={d.id} disabled={d.sent}>
                        {d.sent ? t("documentSent", { name: d.filename }) : d.filename}
                      </option>
                    ))}
                  </select>
                  <div className={ui.formActions}>
                    <button type="submit" className={ui.secondary} disabled={busy || !documentId}>
                      {t("sendDocument")}
                    </button>
                  </div>
                </form>
              ) : null}
            </>
          ) : null}
        </>
      )}
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
