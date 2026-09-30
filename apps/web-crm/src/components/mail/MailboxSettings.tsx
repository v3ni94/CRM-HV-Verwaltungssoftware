"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type OAuthStatus = { client_id: string | null; configured: boolean; source: "tenant" | "environment" | null; redirect_uri: string };
export type Mailbox = {
  id: string;
  address: string;
  kind: string;
  enabled: boolean;
  has_secret: boolean;
  is_default: boolean;
  calendar_enabled: boolean;
  calendar_id: string;
  user_ids: string[];
  last_synced_at: string | null;
  last_error: string | null;
  push_watch_expires_at?: string | null;
  last_push_at?: string | null;
  backfill_status?: string;
  backfill_total?: number | null;
  backfill_done?: number;
  backfill_started_at?: string | null;
  backfill_finished_at?: string | null;
  archive_on_ticket_done?: boolean;
  archive_scope_missing?: boolean;
  is_collective?: boolean;
  // Rückkanal Gmail zu Plattform (M20-08).
  sync_back_enabled?: boolean;
  gmail_last_sync_at?: string | null;
  gmail_state_reconciled_at?: string | null;
  gmail_state_reconcile_status?: string;
  gmail_state_reconcile_counts?: Record<string, number>;
  sync_back_warning?: boolean;
  // Stilvorgaben für KI-Antwortentwürfe (M20-02).
  reply_style?: { tone?: string; rules?: string };
};
export type ReconcilePreview = {
  checked: number;
  would_archive: number;
  would_trash: number;
  would_delete: number;
  would_reopen: number;
  own: number;
  deferred: number;
  samples: { message_id: string; subject: string | null; ticket_id: string | null; action: string }[];
};
export type Member = { user_id: string; email: string; display_name: string; status: string };

function OAuthClientForm({ initial }: { initial: OAuthStatus }) {
  const t = useTranslations("MailSettings");
  const [status, setStatus] = useState(initial);
  const [clientId, setClientId] = useState(initial.client_id ?? "");
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const save = async () => {
    setBusy(true);
    setError(null);
    setSaved(false);
    const res = await bff<OAuthStatus>("/api/bff/mail/oauth/google", {
      method: "PUT",
      body: JSON.stringify({ client_id: clientId.trim(), client_secret: secret.trim() || null }),
    });
    setBusy(false);
    if (res.ok) {
      setStatus(res.data);
      setSecret("");
      setSaved(true);
    } else setError(res.message);
  };
  return (
    <section className={`${ui.card} flex flex-col gap-3`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{t("oauthTitle")}</h2>
        <span className={status.configured ? ui.badgeSuccess : ui.badgeWarning}>
          {status.configured ? t(`source.${status.source ?? "tenant"}`) : t("notConfigured")}
        </span>
      </div>
      <p className="text-xs text-muted">{t("oauthHint")}</p>
      <p className="text-xs text-muted">
        {t("redirectUri")}: <code className="select-all">{status.redirect_uri}</code>
      </p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("clientId")}</span>
        <input className={ui.input} value={clientId} onChange={(e) => setClientId(e.target.value)} autoComplete="off" />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("clientSecret")}</span>
        <input
          className={ui.input}
          type="password"
          value={secret}
          placeholder={status.source === "tenant" ? t("secretKept") : ""}
          onChange={(e) => setSecret(e.target.value)}
          autoComplete="new-password"
        />
      </label>
      <div className="flex items-center gap-3">
        <button type="button" className={ui.primary} disabled={busy || clientId.trim().length < 10} onClick={() => void save()}>
          {t("save")}
        </button>
        {saved ? <span className="text-xs text-success-fg">{t("saved")}</span> : null}
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}

function MailboxRow({
  box,
  members,
  onChange,
  onReconnect,
}: {
  box: Mailbox;
  members: Member[];
  onChange: (next: Mailbox | null) => void;
  onReconnect: () => void;
}) {
  const t = useTranslations("MailSettings");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncInfo, setSyncInfo] = useState<string | null>(null);
  const run = async <T,>(call: () => Promise<Awaited<ReturnType<typeof bff<T>>>>, apply: (data: T) => void) => {
    setBusy(true);
    setError(null);
    const res = await call();
    setBusy(false);
    if (res.ok) apply(res.data);
    else setError(res.message);
  };
  const [preview, setPreview] = useState<ReconcilePreview | null>(null);
  const reconcile = (previewOnly: boolean) =>
    run<ReconcilePreview | { queued: boolean }>(
      () => bff(`/api/bff/mail/mailboxes/${box.id}/reconcile-state`, { method: "POST", body: JSON.stringify({ preview: previewOnly }) }),
      (r) => {
        if (previewOnly) setPreview(r as ReconcilePreview);
        else onChange({ ...box, gmail_state_reconcile_status: "queued" });
      },
    );
  const patch = (body: Partial<Pick<Mailbox, "enabled" | "is_default" | "calendar_enabled" | "sync_back_enabled" | "reply_style">>) =>
    run<Mailbox>(() => bff(`/api/bff/mail/mailboxes/${box.id}`, { method: "PATCH", body: JSON.stringify(body) }), onChange);
  const toggleUser = (userId: string, on: boolean) => {
    const user_ids = on ? [...box.user_ids, userId] : box.user_ids.filter((u) => u !== userId);
    return run<Mailbox>(() => bff(`/api/bff/mail/mailboxes/${box.id}/users`, { method: "PUT", body: JSON.stringify({ user_ids }) }), onChange);
  };
  const sync = () =>
    run<{ fetched: number; created: number; duplicates: number }>(
      () => bff(`/api/bff/mail/mailboxes/${box.id}/sync`, { method: "POST" }),
      (r) => setSyncInfo(t("syncResult", r)),
    );
  const backfill = () => run<Mailbox>(() => bff(`/api/bff/mail/mailboxes/${box.id}/backfill`, { method: "POST" }), onChange);
  const backfillActive = box.backfill_status === "queued" || box.backfill_status === "running";
  // Fortschritt des Vollabrufs: solange er läuft, alle fünf Sekunden die Postfachliste lesen.
  useEffect(() => {
    if (!backfillActive) return;
    const timer = window.setInterval(async () => {
      const res = await bff<Mailbox[]>("/api/bff/mail/mailboxes");
      if (res.ok) {
        const next = res.data.find((b) => b.id === box.id);
        if (next) onChange(next);
      }
    }, 5000);
    return () => window.clearInterval(timer);
  }, [backfillActive, box.id, onChange]);
  const remove = () => {
    if (!window.confirm(t("removeConfirm", { address: box.address }))) return;
    return run<null>(() => bff(`/api/bff/mail/mailboxes/${box.id}`, { method: "DELETE" }), () => onChange(null));
  };
  const fmt = (iso: string) => new Date(iso).toLocaleString("de-DE");
  return (
    <li className="flex flex-col gap-2 border-t border-border py-3 first:border-t-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{box.address}</span>
        <span className={ui.badge}>{box.kind}</span>
        {box.is_default ? <span className={ui.badgeGold}>{t("defaultBadge")}</span> : null}
        {!box.enabled ? <span className={ui.badgeWarning}>{t("disabled")}</span> : null}
        {box.last_error ? <span className={ui.badgeDanger}>{t("errorBadge")}</span> : null}
      </div>
      <p className="text-xs text-muted">
        {box.last_synced_at ? t("lastSynced", { at: fmt(box.last_synced_at) }) : t("neverSynced")}
        {box.last_error ? ` · ${box.last_error}` : ""}
      </p>
      {box.kind === "gmail" && box.archive_scope_missing ? (
        <div className={`${ui.warning} flex flex-wrap items-center justify-between gap-2`} role="status" data-testid="archive-scope-missing">
          <span>{t("archiveScopeMissing")}</span>
          <button type="button" className={ui.primary} disabled={busy} onClick={onReconnect}>
            {t("reconnectGoogle")}
          </button>
        </div>
      ) : null}
      {box.kind === "gmail" ? (
        <p className="text-xs text-muted" data-testid="push-status">
          {box.push_watch_expires_at ? t("pushActiveUntil", { at: fmt(box.push_watch_expires_at) }) : t("pushInactive")}
          {box.last_push_at ? ` · ${t("lastPush", { at: fmt(box.last_push_at) })}` : ""}
        </p>
      ) : null}
      {box.kind === "gmail" && box.backfill_status && box.backfill_status !== "idle" ? (
        <p className="text-xs text-muted" data-testid="backfill-status">
          {t(`backfill.${box.backfill_status}`, {
            done: box.backfill_done ?? 0,
            total: box.backfill_total ?? 0,
            at: box.backfill_finished_at ? fmt(box.backfill_finished_at) : "",
          })}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={box.is_default} disabled={busy} onChange={(e) => void patch({ is_default: e.target.checked })} />
          {t("isDefault")}
        </label>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={box.enabled} disabled={busy} onChange={(e) => void patch({ enabled: e.target.checked })} />
          {t("enabled")}
        </label>
        {box.kind === "gmail" ? (
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={box.calendar_enabled}
              disabled={busy}
              onChange={(e) => void patch({ calendar_enabled: e.target.checked })}
            />
            {t("calendarEnabled")}
          </label>
        ) : null}
        {box.kind === "gmail" ? (
          <label className="flex items-center gap-1.5" title={t("syncBackHint")}>
            <input
              type="checkbox"
              checked={box.sync_back_enabled !== false}
              disabled={busy}
              onChange={(e) => void patch({ sync_back_enabled: e.target.checked })}
              data-testid="sync-back-enabled"
            />
            {t("syncBackEnabled")}
          </label>
        ) : null}
        {box.kind === "gmail" || box.kind === "imap" ? (
          <button type="button" className={ui.button} disabled={busy} onClick={() => void sync()}>
            {t("syncNow")}
          </button>
        ) : null}
        <label className="flex items-center gap-1.5" title={t("replyToneHint")}>
          {t("replyTone")}
          <select
            className={ui.input}
            value={box.reply_style?.tone ?? "sachlich"}
            disabled={busy}
            onChange={(e) => void patch({ reply_style: { ...(box.reply_style ?? {}), tone: e.target.value } })}
            data-testid="reply-tone"
          >
            <option value="formell">{t("replyToneFormell")}</option>
            <option value="sachlich">{t("replyToneSachlich")}</option>
            <option value="freundlich">{t("replyToneFreundlich")}</option>
          </select>
        </label>
        {box.kind === "gmail" ? (
          <button type="button" className={ui.button} disabled={busy} onClick={() => void reconcile(true)} data-testid="reconcile-preview">
            {t("reconcilePreview")}
          </button>
        ) : null}
        {box.kind === "gmail" ? (
          <button
            type="button"
            className={ui.button}
            disabled={busy || box.gmail_state_reconcile_status === "queued" || box.gmail_state_reconcile_status === "running"}
            onClick={() => void reconcile(false)}
            data-testid="reconcile-now"
          >
            {box.gmail_state_reconcile_status === "queued" || box.gmail_state_reconcile_status === "running" ? t("reconcileRunning") : t("reconcileNow")}
          </button>
        ) : null}
        {box.kind === "gmail" ? (
          <button type="button" className={ui.button} disabled={busy || backfillActive} onClick={() => void backfill()}>
            {t("backfillNow")}
          </button>
        ) : null}
        <button type="button" className={ui.danger} disabled={busy} onClick={() => void remove()}>
          {t("remove")}
        </button>
        {syncInfo ? <span className="text-xs text-success-fg">{syncInfo}</span> : null}
      </div>
      {box.kind === "gmail" && box.calendar_enabled ? <p className="text-xs text-muted">{t("calendarHint")}</p> : null}
      {box.kind === "gmail" && box.is_collective ? <p className="text-xs text-muted">{t("collectiveHint")}</p> : null}
      {box.kind === "gmail" && box.gmail_state_reconciled_at ? (
        <p className="text-xs text-muted" data-testid="last-reconcile">
          {t("lastReconcile", {
            at: fmt(box.gmail_state_reconciled_at),
            checked: box.gmail_state_reconcile_counts?.checked ?? 0,
            deviating:
              (box.gmail_state_reconcile_counts?.archived ?? 0) +
              (box.gmail_state_reconcile_counts?.trashed ?? 0) +
              (box.gmail_state_reconcile_counts?.deleted ?? 0) +
              (box.gmail_state_reconcile_counts?.returned ?? 0),
          })}
        </p>
      ) : null}
      {preview ? (
        <div role="dialog" aria-label={t("previewTitle")} className={`${ui.card} flex flex-col gap-2 text-sm`} data-testid="reconcile-preview-dialog">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium">{t("previewTitle")}</span>
            <button type="button" className={ui.button} onClick={() => setPreview(null)}>
              {t("previewClose")}
            </button>
          </div>
          <p className="text-xs text-muted">
            {t("previewSummary", {
              archive: preview.would_archive,
              trash: preview.would_trash,
              delete: preview.would_delete,
              reopen: preview.would_reopen,
              own: preview.own,
            })}
          </p>
          {preview.samples.length > 0 ? (
            <ul className="text-xs text-muted">
              {preview.samples.map((s) => (
                <li key={s.message_id}>
                  {s.action}: {s.subject || "ohne Betreff"}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {box.is_default ? (
        <p className="text-xs text-muted">{t("defaultHint")}</p>
      ) : (
        <fieldset className="flex flex-col gap-1">
          <legend className={ui.label}>{t("access")}</legend>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {members.map((m) => (
              <label key={m.user_id} className="flex items-center gap-1.5">
                <input type="checkbox" checked={box.user_ids.includes(m.user_id)} disabled={busy} onChange={(e) => void toggleUser(m.user_id, e.target.checked)} />
                {m.display_name || m.email}
              </label>
            ))}
          </div>
        </fieldset>
      )}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </li>
  );
}

export function MailboxSettings({ oauth, mailboxes, members }: { oauth: OAuthStatus; mailboxes: Mailbox[]; members: Member[] }) {
  const t = useTranslations("MailSettings");
  const [boxes, setBoxes] = useState(mailboxes);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const connect = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ url: string }>("/api/bff/mail/oauth/google/start", { method: "POST" });
    if (res.ok) window.location.assign(res.data.url);
    else {
      setBusy(false);
      setError(res.message);
    }
  };
  const update = (id: string, next: Mailbox | null) =>
    setBoxes((prev) => (next ? prev.map((b) => (b.id === id ? next : b)) : prev.filter((b) => b.id !== id)));
  return (
    <>
      <OAuthClientForm initial={oauth} />
      <section className={`${ui.card} flex flex-col gap-3`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">{t("mailboxesTitle")}</h2>
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void connect()}>
            {t("connectGoogle")}
          </button>
        </div>
        <p className="text-xs text-muted">{t("mailboxesHint")}</p>
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {boxes.length === 0 ? (
          <p className="text-sm text-muted">{t("empty")}</p>
        ) : (
          <ul>
            {boxes.map((b) => (
              <MailboxRow
                key={b.id}
                box={b}
                members={members.filter((m) => m.status === "active")}
                onChange={(next) => update(b.id, next)}
                onReconnect={() => void connect()}
              />
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
