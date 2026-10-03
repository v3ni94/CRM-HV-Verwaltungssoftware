"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** GAJ-101 (7.5, rule 0.1.7): reverses a posted receivable run by counter postings. The API
 *  requires the approval permission and a reason; posted entries stay untouched. */
export function ReceivableRunReverseForm({ runId, canApprove, onReversed }: { runId: string; canApprove: boolean; onReversed?: () => void }) {
  const t = useTranslations("OperationsMasks.reverse");
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [bookingDate, setBookingDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  if (!canApprove) return null;
  if (done) return <p className={ui.success}>{t("done")}</p>;
  if (!open) {
    return (
      <button type="button" className={ui.button} onClick={() => setOpen(true)}>
        {t("open")}
      </button>
    );
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!window.confirm(t("confirm"))) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/accounting/receivable-runs/${runId}/reverse`, {
      method: "POST",
      body: JSON.stringify({ reason: reason.trim(), booking_date: bookingDate || null }),
    });
    setBusy(false);
    if (res.ok) {
      setDone(true);
      onReversed?.();
    } else setError(res.message);
  }
  return (
    <form onSubmit={submit} className="flex flex-col gap-2" aria-label={t("open")} data-testid="run-reverse-form">
      <p className={ui.help}>{t("hint")}</p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("reason")}</span>
        <textarea className={ui.input} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("date")}</span>
        <input type="date" className={ui.input} value={bookingDate} onChange={(e) => setBookingDate(e.target.value)} />
      </label>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="flex gap-2">
        <button type="submit" className={ui.primary} disabled={busy || reason.trim().length < 3}>
          {t("submit")}
        </button>
        <button type="button" className={ui.button} onClick={() => setOpen(false)} disabled={busy}>
          {t("cancel")}
        </button>
      </div>
    </form>
  );
}
