"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { SecretOnceNotice } from "@/components/settings/SecretOnceNotice";
import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Mail sources of the legacy program (AE38, AF19): list, create, activate, rotate the secret
 *  (shown once, the old one is invalid at once) and the receipt log. */
export type MailSource = {
  id: string;
  name: string;
  active: boolean;
  mailbox_id: string | null;
  auto_ticket: boolean;
  last_received_at: string | null;
  secret_rotated_at: string | null;
  created_at: string;
  delivery_path: string;
};
export type MailSourceEvent = {
  id: string;
  event_id: string;
  message_created: boolean;
  replay_count: number;
  last_replayed_at: string | null;
  created_at: string;
};
type Created = MailSource & { secret: string };

export function MailSourcesAdmin({ initial, loadFailed = false, canManage }: { initial: MailSource[]; loadFailed?: boolean; canManage: boolean }) {
  const t = useTranslations("AF19");
  const [sources, setSources] = useState(initial);
  const [secret, setSecret] = useState<{ title: string; value: string } | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openLog, setOpenLog] = useState<string | null>(null);
  const [logs, setLogs] = useState<Record<string, MailSourceEvent[]>>({});

  function keep(created: Created) {
    const { secret: value, ...rest } = created;
    setSecret({ title: t("mail.secretTitle", { name: rest.name }), value });
    return rest as MailSource;
  }

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (name.trim().length < 1) {
      setError(t("mail.nameRequired"));
      return;
    }
    setBusy(true);
    const res = await bff<Created>("/api/bff/mail/inbound/sources", { method: "POST", body: JSON.stringify({ name: name.trim() }) });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setSources((prev) => [...prev, keep(res.data)]);
    setName("");
  }

  async function rotate(source: MailSource) {
    if (!window.confirm(t("mail.rotateConfirm"))) return;
    setBusy(true);
    setError(null);
    const res = await bff<Created>(`/api/bff/mail/inbound/sources/${source.id}/rotate-secret`, { method: "POST" });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    const next = keep(res.data);
    setSources((prev) => prev.map((s) => (s.id === source.id ? next : s)));
  }

  async function toggle(source: MailSource) {
    setBusy(true);
    setError(null);
    const res = await bff<MailSource>(`/api/bff/mail/inbound/sources/${source.id}`, { method: "PATCH", body: JSON.stringify({ active: !source.active }) });
    setBusy(false);
    if (res.ok) setSources((prev) => prev.map((s) => (s.id === source.id ? { ...s, ...res.data } : s)));
    else setError(res.message);
  }

  async function toggleLog(id: string) {
    if (openLog === id) return setOpenLog(null);
    setOpenLog(id);
    const res = await bff<MailSourceEvent[]>(`/api/bff/mail/inbound/sources/${id}/events?limit=50`);
    if (res.ok) setLogs((prev) => ({ ...prev, [id]: res.data }));
    else setError(t("mail.logLoadError"));
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      {secret ? <SecretOnceNotice title={secret.title} secret={secret.value} onDismiss={() => setSecret(null)} /> : null}
      {canManage ? (
        <form onSubmit={create} className={`${ui.card} flex flex-wrap items-end gap-3`} aria-label={t("mail.new")}>
          <div className="min-w-64 flex-1">
            <label htmlFor="mail-source-name" className={ui.label}>{t("mail.name")}</label>
            <input id="mail-source-name" className={ui.input} value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
          </div>
          <button type="submit" className={ui.primary} disabled={busy}>{t("mail.new")}</button>
        </form>
      ) : (
        <p className="text-xs text-muted">{t("readOnlyHint")}</p>
      )}
      {loadFailed ? <p role="alert" className={ui.alert}>{t("mail.loadError")}</p> : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {sources.length === 0 && !loadFailed ? <p className="text-sm text-muted">{t("mail.empty")}</p> : (
        <div className="overflow-x-auto">
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("mail.name")}</th>
                <th>{t("mail.status")}</th>
                <th>{t("mail.lastReceived")}</th>
                <th>{t("mail.rotated")}</th>
                <th>{t("mail.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <SourceRow key={s.id} s={s} busy={busy} canManage={canManage} open={openLog === s.id} log={logs[s.id]}
                  onLog={() => void toggleLog(s.id)} onToggle={() => void toggle(s)} onRotate={() => void rotate(s)} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SourceRow({ s, busy, canManage, open, log, onLog, onToggle, onRotate }: {
  s: MailSource; busy: boolean; canManage: boolean; open: boolean; log: MailSourceEvent[] | undefined;
  onLog: () => void; onToggle: () => void; onRotate: () => void;
}) {
  const t = useTranslations("AF19");
  return (
    <>
      <tr data-testid={`mail-source-${s.id}`}>
        <td>
          <span className="font-medium">{s.name}</span>
          <p className="break-all text-xs text-muted"><code>{s.delivery_path}</code></p>
        </td>
        <td><StatusPill label={s.active ? t("mail.active") : t("mail.inactive")} variant={s.active ? "success" : "neutral"} /></td>
        <td>{s.last_received_at ? formatDateTime(s.last_received_at) : t("mail.never")}</td>
        <td>{s.secret_rotated_at ? formatDateTime(s.secret_rotated_at) : t("mail.never")}</td>
        <td>
          <div className="flex flex-wrap gap-1">
            <button type="button" className={ui.buttonSm} onClick={onLog}>{open ? t("mail.hideLog") : t("mail.log")}</button>
            {canManage ? <button type="button" className={ui.buttonSm} disabled={busy} onClick={onToggle}>{s.active ? t("mail.deactivate") : t("mail.activate")}</button> : null}
            {canManage ? <button type="button" className={ui.buttonSm} disabled={busy} onClick={onRotate}>{t("mail.rotate")}</button> : null}
          </div>
        </td>
      </tr>
      {open ? (
        <tr data-testid={`mail-source-log-${s.id}`}>
          <td colSpan={5} className="bg-surface-2">
            {log === undefined ? null : log.length === 0 ? <p className="text-sm text-muted">{t("mail.logEmpty")}</p> : (
              <div className="overflow-x-auto"><table className={ui.table}>
                <thead><tr><th>{t("mail.event")}</th><th>{t("mail.receivedAt")}</th><th>{t("mail.created")}</th><th>{t("mail.replays")}</th></tr></thead>
                <tbody>
                  {log.map((e) => (
                    <tr key={e.id}>
                      <td><code className="text-xs">{e.event_id}</code></td>
                      <td>{formatDateTime(e.created_at)}</td>
                      <td>{e.message_created ? t("mail.yes") : t("mail.no")}</td>
                      <td>{e.replay_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            )}
          </td>
        </tr>
      ) : null}
    </>
  );
}
