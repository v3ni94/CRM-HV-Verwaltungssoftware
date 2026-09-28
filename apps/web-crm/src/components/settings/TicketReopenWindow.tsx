"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Regel M19-10: a new email reopens a finished ticket only while its completion lies at most
 *  `ticket_reopen_window_days` calendar days back (`PATCH /tenant/settings`, default 30, 0 to
 *  3650); later emails create a follow up ticket linked to the old one. Every change is written
 *  to the event log as `tenant_settings.updated`. */
export function TicketReopenWindow({ initial, canUpdate }: { initial: number; canUpdate: boolean }) {
  const t = useTranslations("TicketReopenWindow");
  const [days, setDays] = useState(String(initial));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const value = days.trim();
    const n = Number(value);
    if (!/^\d+$/.test(value) || n > 3650) {
      setError(t("invalid"));
      setMessage(null);
      return;
    }
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ ticket_reopen_window_days: number }>("/api/bff/tenant/settings", {
      method: "PATCH",
      body: JSON.stringify({ ticket_reopen_window_days: n }),
    });
    setBusy(false);
    if (res.ok) {
      setDays(String(res.data.ticket_reopen_window_days));
      setMessage(t("saved"));
    } else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="ticket-reopen-window-title">
      <div className="flex flex-col gap-3">
        <h2 id="ticket-reopen-window-title" className={ui.h2}>
          {t("title")}
        </h2>
        <p className={ui.help}>{t("description")}</p>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-sm">
            <span className={ui.label}>{t("label")}</span>
            <input
              type="number"
              min={0}
              max={3650}
              className={ui.input}
              value={days}
              disabled={!canUpdate || busy}
              onChange={(e) => setDays(e.target.value)}
              data-testid="ticket-reopen-window-days"
            />
          </label>
          <button type="button" className={ui.secondary} disabled={!canUpdate || busy} onClick={() => void save()}>
            {t("save")}
          </button>
        </div>
        <p className={ui.help}>{t("hint")}</p>
        {!canUpdate ? <p className={ui.help}>{t("readOnly")}</p> : null}
        {message ? <span className="text-xs text-success-fg">{message}</span> : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
