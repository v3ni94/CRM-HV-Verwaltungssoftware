"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { formatDateTime } from "@/components/portal/types";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type PortalNotice = {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  target_type: string | null;
  target_id: string | null;
  /** Portal route to the subject, derived by the API; null when the subject has no portal page. */
  href: string | null;
  read_at: string | null;
  created_at: string;
};

/** Unread notifications of the portal user (operator 26.09.2026): a click opens the subject,
 *  e.g. the Meldung or the Auftrag, and marks only that entry as read. Nothing is rendered
 *  without unread entries. */
export function PortalNotifications() {
  const t = useTranslations("Portal");
  const [items, setItems] = useState<PortalNotice[]>([]);

  const load = useCallback(async () => {
    const result = await bff<PortalNotice[]>("/api/bff/portal/notifications?unread=true");
    if (result.ok) setItems(result.data);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function readOne(id: string) {
    setItems((prev) => prev.filter((n) => n.id !== id));
    void bff<null>("/api/bff/portal/notifications/read", { method: "POST", body: JSON.stringify([id]) });
  }

  if (items.length === 0) return null;
  const entryClass = "block rounded-md px-3 py-2 text-sm transition duration-150 hover:bg-surface";
  const content = (n: PortalNotice) => (
    <>
      <span className="block font-medium">{n.title}</span>
      {n.body ? <span className="block text-muted">{n.body}</span> : null}
      <span className="block text-xs text-muted">{formatDateTime(n.created_at)}</span>
    </>
  );
  return (
    <section
      aria-labelledby="portal-notifications"
      aria-live="polite"
      className={ui.pageGap}
      data-testid="portal-notifications"
    >
      <h2 id="portal-notifications" className="text-base font-semibold">
        {t("notifications.title")}
      </h2>
      <ul className="flex flex-col gap-1 rounded-lg border border-border">
        {items.map((n) => (
          <li key={n.id}>
            {n.href ? (
              <Link href={n.href} className={entryClass} onClick={() => readOne(n.id)}>
                {content(n)}
              </Link>
            ) : (
              <button type="button" className={`${entryClass} w-full text-left`} title={t("notifications.markRead")} onClick={() => readOne(n.id)}>
                {content(n)}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
