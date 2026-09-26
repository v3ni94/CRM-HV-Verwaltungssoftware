"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { formatDateTime, type WorkOrder } from "@/components/portal/types";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const CLOSED = new Set(["rejected", "cancelled", "accepted", "invoiced"]);

const PROPOSAL_STATES = new Set(["approved", "scheduled"]);

/** Auftrag eines Dienstleisters (M22): ablehnen, Angebot mit Dateianhang, Terminvorschläge an
 *  den Bewohner (A58) oder Termin direkt, Ausführungsbericht mit Fotos als Dokumentverknüpfung,
 *  Rechnungseinreichung. Jede Aktion, die Geld oder den Vertrag betrifft, ist ein Vorschlag zur
 *  Prüfung durch die Verwaltung. */
export function WorkOrderDetail({ order }: { order: WorkOrder }) {
  const t = useTranslations("Orders");
  const tPortal = useTranslations("Portal");
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [quoteAmount, setQuoteAmount] = useState("");
  const [quoteFile, setQuoteFile] = useState<File | null>(null);
  const [appointment, setAppointment] = useState("");
  const [slots, setSlots] = useState(["", "", ""]);
  const [slotNote, setSlotNote] = useState("");
  const [report, setReport] = useState("");
  const [photos, setPhotos] = useState<FileList | null>(null);
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [invoiceDate, setInvoiceDate] = useState("");
  const [invoiceGross, setInvoiceGross] = useState("");
  const [invoiceFile, setInvoiceFile] = useState<File | null>(null);

  async function uploadOne(file: File): Promise<string | null> {
    const form = new FormData();
    form.append("file", file);
    const result = await bff<{ id: string }>("/api/bff/portal/uploads", { method: "POST", body: form });
    if (!result.ok) {
      setError(result.message);
      return null;
    }
    return result.data.id;
  }

  async function run(action: () => Promise<void>) {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      await action();
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  async function decline() {
    if (!window.confirm(t("declineConfirm"))) return;
    await run(async () => {
      const result = await bff(`/api/bff/portal/work-orders/${order.id}/decline`, { method: "POST", body: "{}" });
      if (!result.ok) setError(result.message);
      else setNotice(t("declined"));
    });
  }

  async function submitQuote(event: React.FormEvent) {
    event.preventDefault();
    await run(async () => {
      const amount = quoteAmount.trim().replace(",", ".");
      if (!amount) return;
      let documentId: string | null = null;
      if (quoteFile) {
        documentId = await uploadOne(quoteFile);
        if (documentId === null) return;
      }
      const result = await bff(`/api/bff/portal/work-orders/${order.id}/quote`, {
        method: "POST",
        body: JSON.stringify({ amount, document_id: documentId }),
      });
      if (!result.ok) setError(result.message);
      else setNotice(t("quoteSubmitted"));
    });
  }

  async function submitAppointment(event: React.FormEvent) {
    event.preventDefault();
    await run(async () => {
      if (!appointment) return;
      const result = await bff(`/api/bff/portal/work-orders/${order.id}/appointment`, {
        method: "POST",
        body: JSON.stringify({ scheduled_at: new Date(appointment).toISOString() }),
      });
      if (!result.ok) setError(result.message);
      else setNotice(t("appointmentSubmitted"));
    });
  }

  async function submitProposals(event: React.FormEvent) {
    event.preventDefault();
    await run(async () => {
      const chosen = slots.filter((s) => s.trim() !== "");
      if (chosen.length === 0) {
        setError(t("proposalRequired"));
        return;
      }
      const proposals = chosen.map((s) => ({
        starts_at: new Date(s).toISOString(),
        note: slotNote.trim() || null,
      }));
      const result = await bff(`/api/bff/portal/work-orders/${order.id}/appointment-proposals`, {
        method: "POST",
        body: JSON.stringify({ proposals }),
      });
      if (!result.ok) setError(result.message);
      else {
        setNotice(t("proposalsSubmitted"));
        setSlots(["", "", ""]);
        setSlotNote("");
      }
    });
  }

  async function submitComplete(event: React.FormEvent) {
    event.preventDefault();
    await run(async () => {
      if (report.trim().length < 3) return;
      const ids: string[] = [];
      for (const file of Array.from(photos ?? [])) {
        const id = await uploadOne(file);
        if (id === null) return;
        ids.push(id);
      }
      const result = await bff(`/api/bff/portal/work-orders/${order.id}/complete`, {
        method: "POST",
        body: JSON.stringify({ report: report.trim(), document_ids: ids }),
      });
      if (!result.ok) setError(result.message);
      else setNotice(t("completeSubmitted"));
    });
  }

  async function submitInvoice(event: React.FormEvent) {
    event.preventDefault();
    await run(async () => {
      if (!invoiceFile) {
        setError(t("invoiceDocumentRequired"));
        return;
      }
      if (!invoiceNumber.trim() || !invoiceDate || !invoiceGross.trim()) return;
      const documentId = await uploadOne(invoiceFile);
      if (documentId === null) return;
      const result = await bff(`/api/bff/portal/work-orders/${order.id}/invoice`, {
        method: "POST",
        body: JSON.stringify({
          number: invoiceNumber.trim(),
          invoice_date: invoiceDate,
          gross: invoiceGross.trim().replace(",", "."),
          document_id: documentId,
        }),
      });
      if (!result.ok) setError(result.message);
      else setNotice(t("invoiceSubmitted"));
    });
  }

  return (
    <div className={ui.pageGap}>
      <div className={`${ui.card} flex flex-col gap-2`}>
        <span className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-medium">{order.description}</span>
          <span className={ui.badge}>{t(`status.${order.status}`)}</span>
        </span>
        {order.quote_amount ? <span className="text-sm text-muted">{t("quoteAmount")}: {order.quote_amount} EUR</span> : null}
        {order.scheduled_at ? (
          <span className="text-sm text-muted">
            {t("appointmentDate")}: {formatDateTime(order.scheduled_at)}
          </span>
        ) : null}
        {order.photos.length > 0 ? (
          <span className="text-sm text-muted">
            {t("photosStored")}: {order.photos.map((p) => p.filename).join(", ")}
          </span>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {notice ? <p className={ui.success}>{notice}</p> : null}
      {!CLOSED.has(order.status) ? (
        <button type="button" className={ui.danger} disabled={busy} onClick={() => void decline()}>
          {t("declineAction")}
        </button>
      ) : null}
      <form onSubmit={submitQuote} className={`${ui.card} flex flex-col gap-3`}>
        <h2 className={ui.h2}>{t("quoteSubmit")}</h2>
        <p className={ui.help}>{tPortal("proposalNotice")}</p>
        <div>
          <label htmlFor="quote-amount" className={ui.label}>
            {t("quoteAmount")}
          </label>
          <input
            id="quote-amount"
            inputMode="decimal"
            className={ui.input}
            value={quoteAmount}
            onChange={(e) => setQuoteAmount(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="quote-file" className={ui.label}>
            {t("quoteDocument")}
          </label>
          <input id="quote-file" type="file" className={ui.input} onChange={(e) => setQuoteFile(e.target.files?.[0] ?? null)} />
        </div>
        <button type="submit" className={`${ui.button} ${ui.actionFull}`} disabled={busy}>
          {t("quoteSubmit")}
        </button>
      </form>
      {PROPOSAL_STATES.has(order.status) ? (
        <form onSubmit={submitProposals} className={`${ui.card} flex flex-col gap-3`}>
          <h2 className={ui.h2}>{t("proposalsTitle")}</h2>
          <p className={ui.help}>{t("proposalsHint")}</p>
          {slots.map((value, index) => (
            <div key={index}>
              <label htmlFor={`proposal-${index + 1}`} className={ui.label}>
                {t(`proposal${index + 1}`)}
              </label>
              <input
                id={`proposal-${index + 1}`}
                type="datetime-local"
                className={ui.input}
                value={value}
                onChange={(e) => setSlots(slots.map((s, i) => (i === index ? e.target.value : s)))}
              />
            </div>
          ))}
          <div>
            <label htmlFor="proposal-note" className={ui.label}>
              {t("proposalNote")}
            </label>
            <input id="proposal-note" className={ui.input} maxLength={500} value={slotNote} onChange={(e) => setSlotNote(e.target.value)} />
          </div>
          <button type="submit" className={`${ui.button} ${ui.actionFull}`} disabled={busy}>
            {t("proposalsSubmit")}
          </button>
        </form>
      ) : null}
      {order.appointment_proposals.length > 0 ? (
        <div className={`${ui.card} flex flex-col gap-2`}>
          <h2 className={ui.h2}>{t("proposalsList")}</h2>
          <ul className="flex flex-col gap-1 text-sm">
            {order.appointment_proposals.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  {formatDateTime(p.starts_at)}
                  {p.note ? <span className="text-muted"> ({p.note})</span> : null}
                </span>
                <span className={ui.badge}>{t(`proposalStatus.${p.status}`)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <form onSubmit={submitAppointment} className={`${ui.card} flex flex-col gap-3`}>
        <h2 className={ui.h2}>{t("appointmentDirect")}</h2>
        <div>
          <label htmlFor="appointment-date" className={ui.label}>
            {t("appointmentDate")}
          </label>
          <input
            id="appointment-date"
            type="datetime-local"
            className={ui.input}
            value={appointment}
            onChange={(e) => setAppointment(e.target.value)}
          />
        </div>
        <button type="submit" className={`${ui.button} ${ui.actionFull}`} disabled={busy}>
          {t("appointmentSubmit")}
        </button>
      </form>
      <form onSubmit={submitComplete} className={`${ui.card} flex flex-col gap-3`}>
        <h2 className={ui.h2}>{t("completeSubmit")}</h2>
        <div>
          <label htmlFor="report" className={ui.label}>
            {t("report")}
          </label>
          <textarea id="report" rows={4} className={ui.input} value={report} onChange={(e) => setReport(e.target.value)} />
        </div>
        <div>
          <label htmlFor="photos" className={ui.label}>
            {t("photos")}
          </label>
          <input id="photos" type="file" multiple accept="image/*" className={ui.input} onChange={(e) => setPhotos(e.target.files)} />
        </div>
        <button type="submit" className={`${ui.button} ${ui.actionFull}`} disabled={busy}>
          {t("completeSubmit")}
        </button>
      </form>
      <form onSubmit={submitInvoice} className={`${ui.card} flex flex-col gap-3`}>
        <h2 className={ui.h2}>{t("invoiceSubmit")}</h2>
        <p className={ui.help}>{tPortal("proposalNotice")}</p>
        <div>
          <label htmlFor="invoice-number" className={ui.label}>
            {t("invoiceNumber")}
          </label>
          <input id="invoice-number" className={ui.input} value={invoiceNumber} onChange={(e) => setInvoiceNumber(e.target.value)} />
        </div>
        <div>
          <label htmlFor="invoice-date" className={ui.label}>
            {t("invoiceDate")}
          </label>
          <input id="invoice-date" type="date" className={ui.input} value={invoiceDate} onChange={(e) => setInvoiceDate(e.target.value)} />
        </div>
        <div>
          <label htmlFor="invoice-gross" className={ui.label}>
            {t("invoiceGross")}
          </label>
          <input
            id="invoice-gross"
            inputMode="decimal"
            className={ui.input}
            value={invoiceGross}
            onChange={(e) => setInvoiceGross(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="invoice-file" className={ui.label}>
            {t("invoiceDocument")}
          </label>
          <input id="invoice-file" type="file" className={ui.input} onChange={(e) => setInvoiceFile(e.target.files?.[0] ?? null)} />
        </div>
        <button type="submit" className={`${ui.button} ${ui.actionFull}`} disabled={busy}>
          {t("invoiceSubmit")}
        </button>
      </form>
    </div>
  );
}
