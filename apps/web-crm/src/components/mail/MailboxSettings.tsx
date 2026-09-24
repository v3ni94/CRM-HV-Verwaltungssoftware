"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

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
  user_ids: string[];
  last_synced_at: string | null;
  last_error: string | null;
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

function MailboxRow({ box, members, onChange }: { box: Mailbox; members: Member[]; onChange: (next: Mailbox | null) => void }) {
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
  const patch = (body: Partial<Pick<Mailbox, "enabled" | "is_default">>) =>
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
  const remove = () => {
    if (!window.confirm(t("removeConfirm", { address: box.address }))) return;
    return run<null>(() => bff(`/api/bff/mail/mailboxes/${box.id}`, { method: "DELETE" }), () => onChange(null));
  };
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
        {box.last_synced_at ? t("lastSynced", { at: new Date(box.last_synced_at).toLocaleString("de-DE") }) : t("neverSynced")}
        {box.last_error ? ` · ${box.last_error}` : ""}
      </p>
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
          <button type="button" className={ui.button} disabled={busy} onClick={() => void sync()}>
            {t("syncNow")}
          </button>
        ) : null}
        <button type="button" className={ui.danger} disabled={busy} onClick={() => void remove()}>
          {t("remove")}
        </button>
        {syncInfo ? <span className="text-xs text-success-fg">{syncInfo}</span> : null}
      </div>
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
              <MailboxRow key={b.id} box={b} members={members.filter((m) => m.status === "active")} onChange={(next) => update(b.id, next)} />
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
