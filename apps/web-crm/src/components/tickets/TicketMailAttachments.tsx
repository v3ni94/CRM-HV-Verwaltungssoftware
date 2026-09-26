"use client";

import { useTranslations } from "next-intl";

import { AttachmentReceiptAction } from "@/components/receipts/AttachmentReceiptAction";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type TicketMailAttachment = {
  message_id: string;
  document_id: string;
  filename: string;
  mime_type: string;
  received_at: string | null;
  subject: string | null;
};

/** Attachments of the ticket's inbound mails (M14): PDF and image attachments get the same
 *  "Als Rechnung erfassen" action as the mail view (`POST /receipts/drafts`,
 *  `source=mail_attachment`). Other file types are listed without the action. */
export const RECEIPT_MIME_TYPES = ["application/pdf", "image/png", "image/jpeg"];

export function TicketMailAttachments({ attachments }: { attachments: TicketMailAttachment[] }) {
  const t = useTranslations("Tickets.mailAttachments");
  if (attachments.length === 0) return null;
  return (
    <section className={`${ui.card} flex min-w-0 flex-col gap-2`} data-testid="ticket-mail-attachments">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.help}>{t("hint")}</p>
      <ul className="flex flex-col gap-2 text-sm">
        {attachments.map((a) => (
          <li key={a.document_id} className="flex flex-wrap items-center justify-between gap-2">
            <span className="min-w-0 break-words [overflow-wrap:anywhere]">
              <span className="font-medium">{a.filename}</span>
              <span className="text-xs text-muted">
                {" "}
                {a.received_at ? formatDateTime(a.received_at) : ""}
                {a.subject ? ` · ${a.subject}` : ""}
              </span>
            </span>
            {RECEIPT_MIME_TYPES.includes(a.mime_type) ? (
              <AttachmentReceiptAction messageId={a.message_id} documentId={a.document_id} />
            ) : (
              <span className="text-xs text-muted">{t("unsupported")}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
