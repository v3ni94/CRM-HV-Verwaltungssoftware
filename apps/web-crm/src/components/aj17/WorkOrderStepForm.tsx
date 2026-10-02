"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Folgeschritte je Status, wie vom Router erlaubt (ORDER_FLOW); die Schnittstelle prüft erneut. */
export const ORDER_FLOW: Record<string, string[]> = {
  draft: ["requested", "cancelled"],
  requested: ["quoted", "approved", "rejected", "cancelled"],
  quoted: ["approved", "rejected", "cancelled"],
  approved: ["scheduled", "in_progress", "cancelled"],
  scheduled: ["in_progress", "cancelled"],
  in_progress: ["done"],
  done: ["invoiced", "accepted"],
  invoiced: ["accepted"],
  accepted: [],
  rejected: [],
  cancelled: [],
};
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Auftragsschritt erfassen (GAI-416): Angebot, Freigabe, Termin, Ausführung, Rechnung, Bewertung. */
export function WorkOrderStepForm({ orderId, status, canEdit }: { orderId: string; status: string; canEdit: boolean }) {
  const t = useTranslations("Aj17.step");
  const router = useRouter();
  const [current, setCurrent] = useState(status);
  const next = ORDER_FLOW[current] ?? [];
  const [target, setTarget] = useState("");
  const [note, setNote] = useState("");
  const [quote, setQuote] = useState("");
  const [when, setWhen] = useState("");
  const [report, setReport] = useState("");
  const [invoiceId, setInvoiceId] = useState("");
  const [rating, setRating] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const chosen = target || next[0] || "";

  const submit = async () => {
    const body: Record<string, unknown> = { status: chosen };
    if (note.trim()) body.note = note.trim();
    if (chosen === "quoted") body.quote_amount = quote.trim().replace(",", ".");
    if (chosen === "scheduled" && when) body.scheduled_at = new Date(when).toISOString();
    if (chosen === "done" && report.trim()) body.completion_report = report.trim();
    if (chosen === "invoiced" && UUID.test(invoiceId.trim())) body.invoice_id = invoiceId.trim();
    if (chosen === "accepted" && rating) body.rating = Number(rating);
    setBusy(true);
    setMessage(null);
    const res = await bff(`/api/bff/work-orders/${orderId}/steps`, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setMessage({ ok: false, text: res.message });
      return;
    }
    setCurrent(chosen);
    setTarget("");
    setNote("");
    setMessage({ ok: true, text: t("saved", { status: t(`statuses.${chosen}`) }) });
    router.refresh();
  };

  return (
    <section className={`${ui.card} flex flex-col gap-2`} aria-label={t("title")} data-testid="order-step">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="text-sm" data-testid="order-step-current">{t(`statuses.${current}`)}</p>
      <p className={ui.help}>{t("hint")}</p>
      {canEdit && next.length > 0 ? (
        <>
          <label className="flex max-w-xs flex-col gap-1">
            <span className={ui.label}>{t("status")}</span>
            <select className={ui.input} value={chosen} onChange={(e) => setTarget(e.target.value)}>
              {next.map((s) => (
                <option key={s} value={s}>
                  {t(`statuses.${s}`)}
                </option>
              ))}
            </select>
          </label>
          {chosen === "quoted" ? (
            <label className="flex max-w-xs flex-col gap-1">
              <span className={ui.label}>{t("quoteAmount")}</span>
              <input className={ui.input} inputMode="decimal" value={quote} onChange={(e) => setQuote(e.target.value)} />
            </label>
          ) : null}
          {chosen === "scheduled" ? (
            <label className="flex max-w-xs flex-col gap-1">
              <span className={ui.label}>{t("scheduledAt")}</span>
              <input className={ui.input} type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
            </label>
          ) : null}
          {chosen === "done" ? (
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("completionReport")}</span>
              <textarea className={ui.input} rows={3} value={report} onChange={(e) => setReport(e.target.value)} />
            </label>
          ) : null}
          {chosen === "invoiced" ? (
            <label className="flex max-w-md flex-col gap-1">
              <span className={ui.label}>{t("invoiceId")}</span>
              <input className={ui.input} value={invoiceId} onChange={(e) => setInvoiceId(e.target.value)} />
            </label>
          ) : null}
          {chosen === "accepted" ? (
            <label className="flex max-w-xs flex-col gap-1">
              <span className={ui.label}>{t("rating")}</span>
              <input className={ui.input} type="number" min={1} max={5} value={rating} onChange={(e) => setRating(e.target.value)} />
            </label>
          ) : null}
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("note")}</span>
            <textarea className={ui.input} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <div>
            <button type="button" className={ui.primary} disabled={busy || (chosen === "quoted" && !quote.trim())} onClick={() => void submit()}>
              {t("submit")}
            </button>
          </div>
        </>
      ) : null}
      {message ? (
        <p role={message.ok ? "status" : "alert"} className={message.ok ? ui.success : ui.alert}>
          {message.text}
        </p>
      ) : null}
    </section>
  );
}
