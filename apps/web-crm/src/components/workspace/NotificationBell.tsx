"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type Notice = {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  /** Subject of the notification (ticket, work_order, appointment, message, ...). */
  target_type?: string | null;
  target_id?: string | null;
  /** CRM route to the subject, derived by the API; null when the subject has no page. */
  href?: string | null;
  read_at: string | null;
  created_at: string;
};

const POLL_MS = 60_000;

/** Unread notifications of the current user; polled once a minute. */
export function NotificationBell() {
  const t = useTranslations("Workspace");
  const [items, setItems] = useState<Notice[]>([]);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    const result = await bff<Notice[]>("/api/bff/workspace/notifications?unread=true");
    if (result.ok) setItems(result.data);
  }, []);

  useEffect(() => {
    void load();
    const handle = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(handle);
  }, [load]);

  async function readAll() {
    const result = await bff<null>("/api/bff/workspace/notifications/read", { method: "POST" });
    if (result.ok) setItems([]);
  }

  /** Sammelaktion: alle nicht verpflichtenden Benachrichtigungen für einen Zeitraum stummschalten. */
  async function mute(hours: number | null) {
    const until = hours === null ? null : new Date(Date.now() + hours * 3_600_000).toISOString();
    await bff<unknown>("/api/bff/workspace/notifications/mute", { method: "POST", body: JSON.stringify({ muted_until: until }) });
    setOpen(false);
  }

  /** Operator 26.09.2026: a click opens the subject and marks only this entry as read. */
  function readOne(id: string) {
    setItems((prev) => prev.filter((n) => n.id !== id));
    setOpen(false);
    void bff<null>("/api/bff/workspace/notifications/read", { method: "POST", body: JSON.stringify([id]) });
  }

  const entryClass = "flex min-h-11 flex-col justify-center rounded-lg px-2 py-1.5 text-sm transition duration-150 hover:bg-surface-2 sm:pointer-fine:min-h-0";
  const content = (n: Notice) => (
    <>
      <p className="font-medium">{n.title}</p>
      {n.body ? <p className="text-muted">{n.body}</p> : null}
      <p className="text-xs text-subtle">{formatDateTime(n.created_at)}</p>
    </>
  );

  return (
    <div className="relative">
      {/* Round 44 px icon below sm, a pill from sm (36 px with a mouse as before, 44 px on
          touch), the text label from lg only so the one row header fits a 768 px tablet
          (M31). */}
      <button
        type="button"
        className="relative inline-flex h-11 w-11 items-center justify-center gap-1.5 rounded-full border border-border bg-surface text-sm font-medium text-fg transition duration-150 hover:border-gold hover:bg-surface-2 focus:outline-none focus:ring-2 focus:ring-focus sm:w-auto sm:px-3 sm:pointer-fine:h-9"
        aria-label={t("notifications")}
        aria-expanded={open}
        aria-controls="notifications"
        onClick={() => setOpen((v) => !v)}
      >
        <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4.5 w-4.5" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M5 8a5 5 0 0 1 10 0v3.2l1.2 2.3H3.8L5 11.2Z" strokeLinejoin="round" />
          <path d="M8.3 15.5a1.8 1.8 0 0 0 3.4 0" strokeLinecap="round" />
        </svg>
        <span className="hidden lg:inline">{t("notifications")}</span>
        {items.length > 0 ? (
          <span
            className="absolute -right-0.5 -top-0.5 inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-full bg-accent px-1 text-xs font-semibold text-accent-fg sm:static"
            data-testid="unread-count"
          >
            {items.length}
          </span>
        ) : null}
      </button>
      {open ? (
        <div
          id="notifications"
          className="fixed inset-x-4 top-[calc(var(--mhvp-header-h)+0.5rem)] z-40 max-h-[70vh] overflow-auto rounded-xl border border-border bg-raised p-2 shadow-lg sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:max-h-none sm:w-80"
        >
          {items.length === 0 ? (
            <p className="p-2 text-sm text-muted">{t("noNotifications")}</p>
          ) : (
            <>
              <ul className="flex max-h-80 flex-col gap-1 overflow-auto">
                {items.map((n) => (
                  <li key={n.id}>
                    {n.href ? (
                      <Link href={n.href} className={`${entryClass} focus:outline-none focus:ring-2 focus:ring-focus`} onClick={() => readOne(n.id)} data-testid="notification-link">
                        {content(n)}
                      </Link>
                    ) : (
                      <button type="button" className={`${entryClass} w-full text-left`} title={t("markRead")} onClick={() => readOne(n.id)}>
                        {content(n)}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              <button type="button" className={`${ui.button} mt-2 w-full justify-center`} onClick={() => void readAll()}>
                {t("markAllRead")}
              </button>
            </>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-1 border-t border-border pt-2 text-xs" data-testid="notification-mute">
            <span className="text-muted">{t("muteAll")}</span>
            <button type="button" className={ui.buttonSm} onClick={() => void mute(1)}>
              {t("mute1h")}
            </button>
            <button type="button" className={ui.buttonSm} onClick={() => void mute(24)}>
              {t("mute1d")}
            </button>
            <button type="button" className={ui.buttonSm} onClick={() => void mute(24 * 7)}>
              {t("mute7d")}
            </button>
            <button type="button" className={ui.buttonSm} onClick={() => void mute(null)}>
              {t("unmute")}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
