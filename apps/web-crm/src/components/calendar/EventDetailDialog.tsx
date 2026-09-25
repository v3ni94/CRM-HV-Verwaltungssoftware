"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import type { Attendee } from "@/components/calendar/CreateEventDialog";
import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type CalendarEventDetail = {
  kind: string;
  title: string;
  date: string;
  source: "internal" | "default" | "own";
  google_event_id: string | null;
  calendar_event_id: string | null;
  invite_status: "draft" | "invited" | null;
  attendees: Attendee[];
  is_stale: boolean;
};

/** Event detail with the two rules from M23-05: invitations to external attendees go out only
 *  after an explicit confirmation (never silently), and a Google side change (is_stale) is
 *  shown, never silently overwritten. */
export function EventDetailDialog({ item, onClose, onSent }: { item: CalendarEventDetail; onClose: () => void; onSent: () => void }) {
  const t = useTranslations("Workspace");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canInvite = item.source !== "internal" && item.invite_status === "draft" && item.attendees.length > 0 && item.google_event_id;

  async function sendInvite() {
    setBusy(true);
    const result = await bff(`/api/bff/workspace/calendar/google/${item.source}/${item.google_event_id}/invite`, {
      method: "POST",
      body: JSON.stringify({ confirm: true }),
    });
    setBusy(false);
    setConfirming(false);
    if (result.ok) onSent();
    else setError(result.message);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-fg/40 p-4" role="dialog" aria-modal="true" aria-label={t("eventDetails")}>
      <div className={`${ui.card} flex w-full max-w-md flex-col gap-3`}>
        <h2 className="text-sm font-semibold">{item.title}</h2>
        <p className="text-sm text-muted">{formatDate(item.date)}</p>

        {item.is_stale ? (
          <p role="status" className={ui.notice}>
            {t("staleNotice")}
          </p>
        ) : null}

        {item.attendees.length ? (
          <div className="flex flex-col gap-1">
            <span className={ui.label}>{t("attendees")}</span>
            <ul className="flex flex-wrap gap-1.5">
              {item.attendees.map((a) => (
                <li key={a.email} className={ui.badge}>
                  {a.name || a.email}
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted">
              {item.invite_status === "invited" ? t("inviteSent") : t("inviteNotSentYet")}
            </p>
          </div>
        ) : null}

        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}

        {confirming ? (
          <div role="alertdialog" aria-label={t("confirmInviteTitle")} className={`${ui.notice} flex flex-col gap-2`}>
            <p>{t("confirmInviteBody")}</p>
            <div className={ui.formActions}>
              <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={() => setConfirming(false)} disabled={busy}>
                {t("cancel")}
              </button>
              <button type="button" className={`${ui.primary} ${ui.actionFull}`} onClick={() => void sendInvite()} disabled={busy}>
                {t("confirmInviteAction")}
              </button>
            </div>
          </div>
        ) : null}

        <div className={ui.formActions}>
          <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={onClose}>
            {t("close")}
          </button>
          {canInvite && !confirming ? (
            <button type="button" className={`${ui.primary} ${ui.actionFull}`} onClick={() => setConfirming(true)}>
              {t("sendInvite")}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
