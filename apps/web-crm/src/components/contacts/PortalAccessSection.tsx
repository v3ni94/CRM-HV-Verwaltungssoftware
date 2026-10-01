"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { InvitationQr } from "@/components/portal/InvitationQr";
import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type PortalEmail = { id: string; email: string; is_primary: boolean; is_portal_login: boolean };

/** Row of GET /portal-admin/accounts?contact_id=... (A86): no secret, hash or invitation code. */
export type PortalAccount = {
  id: string;
  contact_id: string;
  email: string;
  status: "invited" | "active" | string;
  locked: boolean;
  invited_at: string;
  invitation_expires_at: string | null;
  activated_at: string | null;
  last_login_at: string | null;
  magic_link_2fa: boolean;
};

type Invited = {
  id: string;
  user_id: string;
  grants: number;
  invitation_token: string;
  invitation_url?: string | null;
};

type Loaded = { state: "loading" } | { state: "error" } | { state: "ready"; accounts: PortalAccount[] };

/** Portal access of a contact (M21, A86): reads the portal accounts of the contact on mount
 *  (GET /portal-admin/accounts?contact_id=..., contacts:read) and shows the status of the model
 *  (invited, active, lock indication); invites via POST /portal-admin/accounts and shows the
 *  invitation once as code, link and QR code. Inviting only with contacts:update (the permission
 *  the API requires). */
export function PortalAccessSection({
  contactId,
  displayName,
  emails,
  canInvite,
}: {
  contactId: string;
  displayName: string;
  emails: PortalEmail[];
  canInvite: boolean;
}) {
  const t = useTranslations("Contacts.portalAccess");
  const loginEmail = emails.find((e) => e.is_portal_login) ?? null;
  const [email, setEmail] = useState(
    (loginEmail ?? emails.find((e) => e.is_primary) ?? emails[0])?.email ?? "",
  );
  const [busy, setBusy] = useState(false);
  const [invited, setInvited] = useState<Invited | null>(null);
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });
  const [exists, setExists] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [letterBusy, setLetterBusy] = useState(false);
  const [securityBusy, setSecurityBusy] = useState(false);
  const [renewBusy, setRenewBusy] = useState(false);

  const load = useCallback(async () => {
    const res = await bff<PortalAccount[]>(
      `/api/bff/portal-admin/accounts?contact_id=${encodeURIComponent(contactId)}`,
    );
    setLoaded(res.ok ? { state: "ready", accounts: res.data ?? [] } : { state: "error" });
  }, [contactId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function invite() {
    const address = email.trim();
    if (!address) {
      setError(t("emailRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    const res = await bff<Invited>("/api/bff/portal-admin/accounts", {
      method: "POST",
      body: JSON.stringify({ contact_id: contactId, email: address, display_name: displayName }),
    });
    setBusy(false);
    if (res.ok) {
      setInvited(res.data);
      await load();
      return;
    }
    if (res.status === 409 && /Portalzugang/.test(res.message)) setExists(true);
    setError(res.message);
  }

  /** M21-01: Einladung als Anschreiben (PDF mit QR-Code, 90 Tage gültiger Code). Rotiert den
   *  Einladungscode auf dem Server, daher POST statt GET (kein wirkungsloser Vorababruf). */
  async function downloadLetter() {
    if (!account) return;
    setLetterBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/portal-admin/accounts/${account.id}/invitation-letter`, {
        method: "POST",
      });
      if (!res.ok) {
        setError(t("letterError"));
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "einladung-kundenportal.pdf";
      a.click();
      URL.revokeObjectURL(url);
      await load();
    } catch {
      setError(t("letterError"));
    } finally {
      setLetterBusy(false);
    }
  }

  /** T13-01: lapsed, never accepted invitation: same endpoint, the API issues a new code and a
   *  new expiry for the existing account (reissued) instead of answering 409. */
  async function renew() {
    if (!account) return;
    setRenewBusy(true);
    setError(null);
    const res = await bff<Invited>("/api/bff/portal-admin/accounts", {
      method: "POST",
      body: JSON.stringify({ contact_id: contactId, email: account.email, display_name: displayName }),
    });
    setRenewBusy(false);
    if (res.ok) {
      setInvited(res.data);
      await load();
      return;
    }
    setError(res.message);
  }

  async function toggleTwoFactor(next: boolean) {
    if (!account) return;
    setSecurityBusy(true);
    setError(null);
    const res = await bff<null>(`/api/bff/portal-admin/accounts/${account.id}/security`, {
      method: "PATCH",
      body: JSON.stringify({ magic_link_2fa: next }),
    });
    setSecurityBusy(false);
    if (res.ok) {
      await load();
      return;
    }
    setError(res.message);
  }

  const account = loaded.state === "ready" ? (loaded.accounts[0] ?? null) : null;
  const hasAccount = account !== null || exists;
  const expired =
    account !== null &&
    account.status === "invited" &&
    account.invitation_expires_at !== null &&
    new Date(account.invitation_expires_at).getTime() <= Date.now();
  const status =
    loaded.state === "loading"
      ? t("status.loading")
      : loaded.state === "error"
        ? exists
          ? t("status.exists")
          : t("status.loadError")
        : account
          ? `${account.status === "active" ? t("status.active") : t("status.invited")}${
              account.locked ? `, ${t("status.locked")}` : ""
            }`
          : exists
            ? t("status.exists")
            : t("status.none");

  return (
    <section className="flex flex-col gap-2" data-testid="contact-portal-access">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">{t("title")}</h2>
        <span className={hasAccount ? ui.badgeGold : ui.badge} data-testid="contact-portal-status">
          {status}
        </span>
      </div>
      {account ? (
        <dl className="text-xs text-subtle" data-testid="contact-portal-account">
          <div>{t("accountEmail", { email: account.email })}</div>
          {account.status === "active" && account.activated_at ? (
            <div>{t("activatedAt", { date: formatDate(account.activated_at) })}</div>
          ) : (
            <div>
              {t("invitedAt", {
                date: formatDate(account.invited_at),
                until: formatDate(account.invitation_expires_at),
              })}
            </div>
          )}
          {account.last_login_at ? (
            <div>{t("lastLogin", { date: formatDateTime(account.last_login_at) })}</div>
          ) : null}
        </dl>
      ) : null}
      {account && canInvite ? (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className={ui.button}
            disabled={letterBusy}
            onClick={() => void downloadLetter()}
            data-testid="contact-portal-letter"
          >
            {letterBusy ? t("letterBusy") : t("letterButton")}
          </button>
          {expired ? (
            <button
              type="button"
              className={ui.button}
              disabled={renewBusy}
              onClick={() => void renew()}
              data-testid="contact-portal-renew"
            >
              {renewBusy ? t("renewBusy") : t("renewButton")}
            </button>
          ) : null}
          <label className="flex items-center gap-2 text-xs text-subtle">
            <input
              type="checkbox"
              checked={account.magic_link_2fa}
              disabled={securityBusy}
              onChange={(e) => void toggleTwoFactor(e.target.checked)}
            />
            {t("twoFactorEmail")}
          </label>
        </div>
      ) : null}
      {expired && canInvite ? <p className={ui.help}>{t("expiredHint")}</p> : null}
      {!canInvite ? (
        <p className={ui.help}>{t("noPermission")}</p>
      ) : invited || hasAccount || loaded.state === "loading" ? null : (
        <div className="flex flex-col gap-2 md:flex-row md:items-end">
          <div className="flex-1">
            <label htmlFor="contact-portal-email" className={ui.label}>
              {t("email")}
            </label>
            <input
              id="contact-portal-email"
              type="email"
              className={ui.input}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              list="contact-portal-emails"
            />
            <datalist id="contact-portal-emails">
              {emails.map((e) => (
                <option key={e.id} value={e.email} />
              ))}
            </datalist>
          </div>
          <button type="button" className={ui.button} disabled={busy} onClick={() => void invite()}>
            {t("invite")}
          </button>
        </div>
      )}
      {invited ? (
        <div className={ui.notice} data-testid="contact-invitation">
          <p className="font-medium">{t("tokenTitle")}</p>
          <p>{t("tokenHelp")}</p>
          <code className="mt-1 block select-all break-all rounded bg-surface px-2 py-1 font-mono text-xs">
            {invited.invitation_token}
          </code>
          <InvitationQr url={invited.invitation_url} title={t("linkTitle")} alt={t("qrAlt")} />
          {!invited.invitation_url ? <p className="text-xs text-subtle">{t("noPortalUrl")}</p> : null}
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <p className={ui.help}>{t("help")}</p>
    </section>
  );
}
