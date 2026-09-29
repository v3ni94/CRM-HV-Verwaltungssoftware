"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import type { InvoiceCopyRequest } from "./LexofficeInvoiceCopyCard";

/** Chip on the mail suggestion (INT-LEXO-01): shown when the platform detected an invoice
 *  copy request for this mail. Source of truth is the request row at the ticket
 *  (`GET /integrations/lexoffice/tickets/{id}/invoice-copies`); the stored suggestion intent
 *  is the fallback before a ticket exists. The chip only links, it never triggers a lookup. */
export function LexofficeInvoiceCopyChip({
  messageId,
  ticketId,
  intent,
  invoiceNumber,
}: {
  messageId: string;
  ticketId: string | null;
  intent?: string | null;
  invoiceNumber?: string | null;
}) {
  const t = useTranslations("Lexoffice.chip");
  const [request, setRequest] = useState<InvoiceCopyRequest | null>(null);

  useEffect(() => {
    if (!ticketId) return;
    let cancelled = false;
    void bff<InvoiceCopyRequest[]>(`/api/bff/integrations/lexoffice/tickets/${ticketId}/invoice-copies`).then((res) => {
      if (cancelled || !res.ok) return;
      setRequest(res.data.find((r) => r.message_id === messageId && r.status !== "rejected") ?? null);
    });
    return () => {
      cancelled = true;
    };
  }, [ticketId, messageId]);

  const detected = request !== null || intent === "invoice_copy_requested";
  if (!detected) return null;
  const number = request?.invoice_number ?? invoiceNumber ?? null;
  return (
    <span className={ui.badge} data-testid="lexoffice-invoice-copy-chip">
      {number ? t("withNumber", { number }) : t("detected")}
      {ticketId ? (
        <Link href={`/tickets/${ticketId}`} className="hover:underline">
          {t("openTicket")}
        </Link>
      ) : null}
    </span>
  );
}
