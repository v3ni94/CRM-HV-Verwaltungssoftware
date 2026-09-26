"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** M20-03 emergency brake (operator decision 26.09.2026): when on, every ticket reply of the
 *  tenant needs approval by a second person regardless of the per member flag
 *  (`PATCH /tenant/settings`, field `ticket_reply_approval_all`, default off). Off means
 *  members with the approve permission and without a flag send their ticket replies directly.
 *  Every change is written to the event log as `tenant_settings.updated`. */
export function TicketReplyApprovalAll({ initial, canUpdate }: { initial: boolean; canUpdate: boolean }) {
  const t = useTranslations("TicketReplyApprovalAll");
  const [enabled, setEnabled] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle(next: boolean) {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ ticket_reply_approval_all: boolean }>("/api/bff/tenant/settings", {
      method: "PATCH",
      body: JSON.stringify({ ticket_reply_approval_all: next }),
    });
    setBusy(false);
    if (res.ok) {
      setEnabled(res.data.ticket_reply_approval_all);
      setMessage(t("saved"));
    } else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="ticket-reply-approval-all-title">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="ticket-reply-approval-all-title" className={ui.h2}>
            {t("title")}
          </h2>
          <span
            className={`rounded-md px-2 py-0.5 text-xs font-medium ${enabled ? "bg-warning-bg text-warning-fg" : "bg-surface text-muted"}`}
            data-testid="ticket-reply-approval-all-status"
          >
            {enabled ? t("status.on") : t("status.off")}
          </span>
        </div>
        <p className={ui.help}>{t("description")}</p>
        <p className={ui.help}>{t("members")}</p>
        <p className="text-xs text-warning-fg">{t("risk")}</p>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} disabled={!canUpdate || busy} onChange={(e) => void toggle(e.target.checked)} />
          <span>{t("label")}</span>
        </label>
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
