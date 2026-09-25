"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { parseGermanDecimal } from "@/lib/format";
import { ui } from "@/lib/ui";

type Panel = "decline" | "quote" | "appointment" | "complete" | null;

/**
 * Actions of one work order, gated by the API status flow (ORDER_FLOW):
 * decline from requested/quoted, quote from requested, appointment after approval,
 * completion from scheduled/in_progress. The decline endpoint takes no reason (no body).
 */
export function WorkOrderActions({ orderId, status }: { orderId: string; status: string }) {
  const t = useTranslations("Orders");
  const router = useRouter();
  const [panel, setPanel] = useState<Panel>(null);
  const [amount, setAmount] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [report, setReport] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const canDecline = status === "requested" || status === "quoted";
  const canQuote = status === "requested";
  const canAppointment = status === "approved";
  const canComplete = status === "scheduled" || status === "in_progress";

  function open(next: Panel) {
    setPanel(panel === next ? null : next);
    setFieldError(null);
    setError(null);
    setDone(false);
  }

  async function post(path: string, body?: unknown): Promise<void> {
    setSubmitting(true);
    const result = await bff<unknown>(`/api/bff/portal/work-orders/${orderId}/${path}`, {
      method: "POST",
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
    setSubmitting(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setDone(true);
    setPanel(null);
    router.refresh();
  }

  async function onDecline() {
    setError(null);
    await post("decline");
  }

  async function onQuote(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const decimal = parseGermanDecimal(amount);
    if (decimal === null || Number(decimal) <= 0) {
      setFieldError(t("quoteAmountInvalid"));
      return;
    }
    setFieldError(null);
    await post("quote", { amount: decimal });
  }

  async function onAppointment(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!scheduledAt) {
      setFieldError(t("appointmentInvalid"));
      return;
    }
    setFieldError(null);
    await post("appointment", { scheduled_at: new Date(scheduledAt).toISOString() });
  }

  async function onComplete(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (report.trim().length < 3) {
      setFieldError(t("completeReportRequired"));
      return;
    }
    setFieldError(null);
    const photoIds: string[] = [];
    if (photo) {
      setSubmitting(true);
      const data = new FormData();
      data.append("file", photo);
      const upload = await bff<{ id: string }>("/api/bff/portal/uploads", { method: "POST", body: data });
      setSubmitting(false);
      if (!upload.ok) {
        setError(upload.message);
        return;
      }
      photoIds.push(upload.data.id);
    }
    await post("complete", { report: report.trim(), photo_document_ids: photoIds });
  }

  if (!canDecline && !canQuote && !canAppointment && !canComplete) {
    return done ? (
      <p role="status" className={ui.success}>
        {t("actionDone")}
      </p>
    ) : null;
  }

  return (
    <div className="mt-3 flex flex-col gap-3">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {done ? (
        <p role="status" className={ui.success}>
          {t("actionDone")}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {canQuote ? (
          <button type="button" className={ui.button} onClick={() => open("quote")}>
            {t("quote")}
          </button>
        ) : null}
        {canAppointment ? (
          <button type="button" className={ui.button} onClick={() => open("appointment")}>
            {t("appointment")}
          </button>
        ) : null}
        {canComplete ? (
          <button type="button" className={ui.button} onClick={() => open("complete")}>
            {t("complete")}
          </button>
        ) : null}
        {canDecline ? (
          <button type="button" className={ui.button} onClick={() => open("decline")}>
            {t("decline")}
          </button>
        ) : null}
      </div>
      {panel === "decline" ? (
        <div className="flex flex-wrap gap-2">
          <button type="button" className={ui.danger} disabled={submitting} onClick={onDecline}>
            {submitting ? t("submitting") : t("declineConfirm")}
          </button>
          <button type="button" className={ui.button} onClick={() => setPanel(null)}>
            {t("cancel")}
          </button>
        </div>
      ) : null}
      {panel === "quote" ? (
        <form onSubmit={onQuote} noValidate className="flex flex-col gap-2" aria-label={t("quote")}>
          <label htmlFor={`quote-amount-${orderId}`} className={ui.label}>
            {t("quoteAmount")}
          </label>
          <input
            id={`quote-amount-${orderId}`}
            type="text"
            inputMode="decimal"
            className={ui.input}
            aria-invalid={!!fieldError}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          {fieldError ? <p className={ui.error}>{fieldError}</p> : null}
          <div className="flex flex-wrap gap-2">
            <button type="submit" className={ui.primary} disabled={submitting}>
              {submitting ? t("submitting") : t("quoteSubmit")}
            </button>
            <button type="button" className={ui.button} onClick={() => setPanel(null)}>
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : null}
      {panel === "appointment" ? (
        <form onSubmit={onAppointment} noValidate className="flex flex-col gap-2" aria-label={t("appointment")}>
          <label htmlFor={`appointment-at-${orderId}`} className={ui.label}>
            {t("appointmentAt")}
          </label>
          <input
            id={`appointment-at-${orderId}`}
            type="datetime-local"
            className={ui.input}
            aria-invalid={!!fieldError}
            value={scheduledAt}
            onChange={(e) => setScheduledAt(e.target.value)}
          />
          {fieldError ? <p className={ui.error}>{fieldError}</p> : null}
          <div className="flex flex-wrap gap-2">
            <button type="submit" className={ui.primary} disabled={submitting}>
              {submitting ? t("submitting") : t("appointmentSubmit")}
            </button>
            <button type="button" className={ui.button} onClick={() => setPanel(null)}>
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : null}
      {panel === "complete" ? (
        <form onSubmit={onComplete} noValidate className="flex flex-col gap-2" aria-label={t("complete")}>
          <label htmlFor={`complete-report-${orderId}`} className={ui.label}>
            {t("completeReport")}
          </label>
          <textarea
            id={`complete-report-${orderId}`}
            rows={3}
            className={ui.input}
            aria-invalid={!!fieldError}
            value={report}
            onChange={(e) => setReport(e.target.value)}
          />
          {fieldError ? <p className={ui.error}>{fieldError}</p> : null}
          <label htmlFor={`complete-photo-${orderId}`} className={ui.label}>
            {t("completePhoto")}
          </label>
          <input
            id={`complete-photo-${orderId}`}
            type="file"
            accept="image/*"
            className={ui.input}
            onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
          />
          <div className="flex flex-wrap gap-2">
            <button type="submit" className={ui.primary} disabled={submitting}>
              {submitting ? t("submitting") : t("completeSubmit")}
            </button>
            <button type="button" className={ui.button} onClick={() => setPanel(null)}>
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}
