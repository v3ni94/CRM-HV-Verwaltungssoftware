"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type Notice = {
  id: string;
  kind: string;
  title: string;
  body: string | null;
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

  return (
    <div className="relative">
      <button
        type="button"
        className="relative inline-flex h-9 items-center gap-1.5 rounded-full border border-border bg-bg px-3 text-sm font-medium text-fg transition duration-150 hover:border-gold hover:bg-surface focus:outline-none focus:ring-2 focus:ring-gold/40"
        aria-expanded={open}
        aria-controls="notifications"
        onClick={() => setOpen((v) => !v)}
      >
        <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4.5 w-4.5" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M5 8a5 5 0 0 1 10 0v3.2l1.2 2.3H3.8L5 11.2Z" strokeLinejoin="round" />
          <path d="M8.3 15.5a1.8 1.8 0 0 0 3.4 0" strokeLinecap="round" />
        </svg>
        {t("notifications")}
        {items.length > 0 ? (
          <span
            className="inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-full bg-accent px-1 text-xs font-semibold text-accent-fg"
            data-testid="unread-count"
          >
            {items.length}
          </span>
        ) : null}
      </button>
      {open ? (
        <div id="notifications" className="absolute right-0 z-40 mt-2 w-80 rounded-xl border border-border bg-bg p-2 shadow-lg">
          {items.length === 0 ? (
            <p className="p-2 text-sm text-muted">{t("noNotifications")}</p>
          ) : (
            <>
              <ul className="flex max-h-80 flex-col gap-1 overflow-auto">
                {items.map((n) => (
                  <li key={n.id} className="rounded-lg px-2 py-1.5 text-sm transition duration-150 hover:bg-surface">
                    <p className="font-medium">{n.title}</p>
                    {n.body ? <p className="text-muted">{n.body}</p> : null}
                    <p className="text-xs text-subtle">{formatDateTime(n.created_at)}</p>
                  </li>
                ))}
              </ul>
              <button type="button" className={`${ui.button} mt-2 w-full justify-center`} onClick={() => void readAll()}>
                {t("markAllRead")}
              </button>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
