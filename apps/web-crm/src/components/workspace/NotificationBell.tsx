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
        className={ui.button}
        aria-expanded={open}
        aria-controls="notifications"
        onClick={() => setOpen((v) => !v)}
      >
        {t("notifications")}
        {items.length > 0 ? (
          <span className="rounded bg-accent px-1 text-xs text-accent-fg" data-testid="unread-count">
            {items.length}
          </span>
        ) : null}
      </button>
      {open ? (
        <div id="notifications" className="absolute right-0 z-40 mt-1 w-80 rounded border border-border bg-bg p-2 shadow-lg">
          {items.length === 0 ? (
            <p className="text-sm text-muted">{t("noNotifications")}</p>
          ) : (
            <>
              <ul className="flex max-h-80 flex-col gap-2 overflow-auto">
                {items.map((n) => (
                  <li key={n.id} className="text-sm">
                    <p className="font-medium">{n.title}</p>
                    {n.body ? <p className="text-muted">{n.body}</p> : null}
                    <p className="text-xs text-muted">{formatDateTime(n.created_at)}</p>
                  </li>
                ))}
              </ul>
              <button type="button" className={`${ui.button} mt-2`} onClick={() => void readAll()}>
                {t("markAllRead")}
              </button>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
