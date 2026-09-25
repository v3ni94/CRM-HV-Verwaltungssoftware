"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** "Als Rechnung zuordnen" (M11-finapi Stage 3): sets the ticket's category to "invoice" and
 *  files the invoice's original document into the property's Google Drive year folder
 *  (`POST /tickets/{id}/attach-invoice`). Requires the ticket's own property; disabled
 *  without one instead of failing silently. */
export function TicketAttachInvoiceButton({ ticketId, hasProperty }: { ticketId: string; hasProperty: boolean }) {
  const t = useTranslations("TicketInvoice");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [invoiceId, setInvoiceId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function attach() {
    setBusy(true);
    setError(null);
    setMessage(null);
    const result = await bff(`/api/bff/tickets/${ticketId}/attach-invoice`, {
      method: "POST",
      body: JSON.stringify({ invoice_id: invoiceId.trim() }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message || t("error"));
      return;
    }
    setMessage(t("attached"));
    setInvoiceId("");
    router.refresh();
  }

  if (!open) {
    return (
      <button type="button" className={ui.buttonSm} disabled={!hasProperty} onClick={() => setOpen(true)}>
        {t("attach")}
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {message ? <p className={ui.notice}>{message}</p> : null}
      <label className="flex flex-col gap-1 text-sm">
        {t("invoiceId")}
        <input className={ui.input} value={invoiceId} onChange={(e) => setInvoiceId(e.target.value)} />
      </label>
      <div className="flex gap-2">
        <button type="button" className={ui.primary} disabled={busy || !invoiceId.trim()} onClick={attach}>
          {t("attach")}
        </button>
        <button type="button" className={ui.buttonSm} onClick={() => setOpen(false)}>
          ×
        </button>
      </div>
    </div>
  );
}
