"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Account = { id: string; status: string; locked: boolean };

export type PortalState = "none" | "invited" | "active" | "locked";

/** Overall portal state of a contact from its portal accounts: locked wins over active, active
 *  over invited, no account is "none". Exported for the tests. */
export function portalState(accounts: Account[]): PortalState {
  if (accounts.length === 0) return "none";
  if (accounts.some((a) => a.status === "active" && !a.locked)) return "active";
  if (accounts.some((a) => a.locked)) return "locked";
  return "invited";
}

/** Read only portal status next to the contact name (M3-07, 6.1 portal_account; the account
 *  itself lives in the platform module). Reads GET /portal-admin/accounts?contact_id=...
 *  (contacts:read) and links to the tab with the invitation. Without a readable answer nothing
 *  is shown, the badge never blocks the page. */
export function PortalStatusBadge({ contactId }: { contactId: string }) {
  const t = useTranslations("PortalStatusBadge");
  const [state, setState] = useState<PortalState | null>(null);

  useEffect(() => {
    let cancelled = false;
    void bff<Account[]>(`/api/bff/portal-admin/accounts?contact_id=${encodeURIComponent(contactId)}`).then((res) => {
      if (!cancelled && res.ok) setState(portalState(res.data ?? []));
    });
    return () => {
      cancelled = true;
    };
  }, [contactId]);

  if (state === null) return null;
  const tone = state === "active" ? ui.badgeSuccess : state === "locked" ? ui.badgeDanger : state === "invited" ? ui.badgeWarning : ui.badge;
  return (
    <Link href={`/kontakte/${contactId}?tab=freigaben`} className={tone} data-testid="portal-status-badge" title={t("hint")}>
      {t(state)}
    </Link>
  );
}
