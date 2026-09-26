"use client";

import { useState } from "react";

import { InvitationQr } from "@/components/portal/InvitationQr";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import type { Item, PortalAccess } from "./types";

type Granted = PortalAccess & {
  account_id: string;
  invitation_token: string | null;
  invitation_url?: string | null;
  email: string | null;
};

/** Portal access of a participant (M30 Stufe 3): create or renew the grant, show the
 *  invitation once, end the access. Only for participants linked to a CRM contact. */
export function PortalAccessBox({
  base,
  item,
  disabled,
  onChanged,
  onError,
  t,
}: {
  base: string;
  item: Item;
  disabled: boolean;
  onChanged: () => Promise<void>;
  onError: (m: string | null) => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}) {
  const access = (item.portal_access ?? null) as PortalAccess | null;
  const [email, setEmail] = useState(String(item.email ?? ""));
  const [busy, setBusy] = useState(false);
  const [granted, setGranted] = useState<Granted | null>(null);
  const url = `${base}/participants/${item.id}/portal-access`;

  async function grant() {
    setBusy(true);
    onError(null);
    const res = await bff<Granted>(url, {
      method: "POST",
      body: JSON.stringify(access ? {} : { email: email.trim() || null }),
    });
    setBusy(false);
    if (res.ok) {
      setGranted(res.data);
      await onChanged();
    } else onError(res.message);
  }

  async function revoke() {
    if (!window.confirm(t("portalAccess.confirmRevoke"))) return;
    setBusy(true);
    const res = await bff(url, { method: "DELETE" });
    setBusy(false);
    if (res.ok) {
      setGranted(null);
      await onChanged();
    } else onError(res.message);
  }

  const statusText = access
    ? access.right === "read" && access.valid_to
      ? t("portalAccess.status.read", { date: access.valid_to.split("-").reverse().join(".") })
      : access.active
        ? t(`portalAccess.status.${access.account_status === "invited" ? "invited" : "active"}`)
        : t("portalAccess.status.inactive")
    : null;

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border-soft bg-surface p-3" data-testid="portal-access">
      <div className="flex flex-wrap items-center gap-2">
        <span className="mhvp-label">{t("portalAccess.title")}</span>
        {statusText ? <span className={access?.active ? ui.badgeGold : ui.badge}>{statusText}</span> : null}
      </div>
      {!access && !disabled ? (
        <div className="flex flex-col gap-2 md:flex-row md:items-end">
          <div className="flex-1">
            <label htmlFor={`portal-email-${item.id}`} className={ui.label}>
              {t("portalAccess.email")}
            </label>
            <input
              id={`portal-email-${item.id}`}
              type="email"
              className={ui.input}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <button type="button" className={ui.button} disabled={busy} onClick={grant}>
            {t("portalAccess.grant")}
          </button>
        </div>
      ) : null}
      {access && !disabled ? (
        <div className="flex flex-wrap gap-2">
          {!access.active || access.right === "read" ? (
            <button type="button" className={ui.buttonSm} disabled={busy} onClick={grant}>
              {t("portalAccess.renew")}
            </button>
          ) : null}
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={revoke}>
            {t("portalAccess.revoke")}
          </button>
        </div>
      ) : null}
      {granted?.invitation_token ? (
        <div className={ui.notice} data-testid="invitation-token">
          <p className="font-medium">{t("portalAccess.tokenTitle")}</p>
          <p>{t("portalAccess.tokenHelp")}</p>
          <code className="mt-1 block select-all break-all rounded bg-bg px-2 py-1 font-mono text-xs">
            {granted.invitation_token}
          </code>
          <InvitationQr url={granted.invitation_url} title={t("portalAccess.linkTitle")} alt={t("portalAccess.qrAlt")} />
          {granted.email ? <p className="text-xs text-subtle">{granted.email}</p> : null}
        </div>
      ) : granted ? (
        <p className="text-sm text-muted">{t("portalAccess.done")}</p>
      ) : null}
      <p className={ui.help}>{t("portalAccess.help")}</p>
    </div>
  );
}
