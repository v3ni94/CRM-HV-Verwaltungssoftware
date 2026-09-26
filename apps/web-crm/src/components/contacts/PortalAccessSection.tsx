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

  const account = loaded.state === "ready" ? (loaded.accounts[0] ?? null) : null;
  const hasAccount = account !== null || exists;
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
          <code className="mt-1 block select-all break-all rounded bg-bg px-2 py-1 font-mono text-xs">
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
