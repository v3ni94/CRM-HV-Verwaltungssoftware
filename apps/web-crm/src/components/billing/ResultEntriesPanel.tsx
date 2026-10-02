"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** GAF-13: create the result entries (drafts) of a due statement. Gate G3 and the status
 *  check run in the API; a refusal is shown unchanged. Nothing is posted by this action. */
export function ResultEntriesPanel({ id, status }: { id: string; status: string }) {
  const t = useTranslations("BillingExtra.resultEntries");
  const [bookingDate, setBookingDate] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (status !== "due") return <p className={ui.help}>{t("onlyDue")}</p>;
  async function create() {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<{ entry_ids: string[] }>(`/api/bff/statements/${id}/result-entries`, {
      method: "POST",
      body: JSON.stringify({ booking_date: bookingDate, due_date: dueDate }),
    });
    setBusy(false);
    if (res.ok) setMessage(t("created", { n: res.data?.entry_ids?.length ?? 0 }));
    else setError(res.message);
  }
  return (
    <section className="flex flex-col gap-2" data-testid="result-entries">
      <h3 className={ui.h2}>{t("title")}</h3>
      <p className={ui.notice}>{t("notice")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("bookingDate")}</span>
          <input className={ui.input} type="date" value={bookingDate} onChange={(e) => setBookingDate(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("dueDate")}</span>
          <input className={ui.input} type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
        </label>
        <button type="button" className={ui.primary} disabled={busy || !bookingDate || !dueDate} onClick={() => void create()}>
          {t("create")}
        </button>
      </div>
      {message ? (
        <p role="status" className={ui.success}>
          {message}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
