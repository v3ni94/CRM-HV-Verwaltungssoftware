"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { AttachmentReceiptAction } from "@/components/receipts/AttachmentReceiptAction";
import { RECEIPT_MIME_TYPES } from "@/components/tickets/TicketMailAttachments";
import { SafeHtml, SafeLine, SafeText } from "@/components/ui/SafeText";
import { formatDateTime } from "@/lib/format";
import { formatBytes, isPreviewable, splitQuoted } from "@/lib/mailText";
import { ui } from "@/lib/ui";

export type ThreadAttachment = {
  document_id: string;
  filename: string | null;
  mime_type: string | null;
  size: number | null;
  missing: boolean;
};

export type ThreadMessage = {
  id: string;
  direction: "in" | "out";
  status: string;
  from_address: string | null;
  to_addresses: string[];
  cc_addresses: string[];
  subject: string | null;
  body: string | null;
  body_html: string | null;
  received_at: string | null;
  sent_at: string | null;
  created_at?: string | null;
  mailbox_address: string | null;
  rejection_note: string | null;
  send_error: string | null;
  attachments: ThreadAttachment[];
};

/** Display status of a message: outbound drafts, pending, sent, or failed (send error
 *  recorded at approval); inbound messages keep their intake status. */
export function displayStatus(message: ThreadMessage): string {
  if (message.direction === "out" && message.send_error && message.status !== "sent") return "failed";
  return message.status;
}

export function messageTime(message: ThreadMessage): string | null {
  return message.direction === "in" ? message.received_at : (message.sent_at ?? message.created_at ?? null);
}

function statusClass(status: string): string {
  if (status === "sent" || status === "done") return ui.badgeSuccess;
  if (status === "pending") return ui.badgeWarning;
  if (status === "failed") return ui.badgeDanger;
  return ui.badge;
}

function AttachmentRow({ ticketId, messageId, direction, attachment }: { ticketId: string; messageId: string; direction: "in" | "out"; attachment: ThreadAttachment }) {
  const t = useTranslations("Tickets.mailThread");
  const ta = useTranslations("Tickets.mailAttachments");
  const [open, setOpen] = useState(false);
  const base = `/api/bff/tickets/${ticketId}/mail-attachments/${attachment.document_id}/content`;
  const name = attachment.filename || attachment.document_id;
  const previewable = !attachment.missing && isPreviewable(attachment.mime_type);
  const isImage = String(attachment.mime_type ?? "").startsWith("image/");
  return (
    <li className="flex min-w-0 flex-col gap-1" data-testid="ticket-mail-attachment">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <SafeLine className="font-medium">{name}</SafeLine>
        <span className="text-xs text-muted">
          {attachment.missing ? t("attachmentMissing") : `${formatBytes(attachment.size)}${attachment.mime_type ? ` · ${attachment.mime_type}` : ""}`}
        </span>
        {previewable ? (
          <button type="button" className={ui.buttonSm} onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            {open ? t("closePreview") : t("preview")}
          </button>
        ) : null}
        {!attachment.missing ? (
          <a className={ui.buttonSm} href={`${base}?download=true`} download={name}>
            {t("download")}
          </a>
        ) : null}
        {direction === "in" && !attachment.missing && RECEIPT_MIME_TYPES.includes(String(attachment.mime_type)) ? (
          <AttachmentReceiptAction messageId={messageId} documentId={attachment.document_id} label={ta("receipt")} />
        ) : null}
      </div>
      {open && previewable ? (
        <div className="max-w-full overflow-hidden rounded-md border border-border bg-surface" data-testid="ticket-mail-attachment-preview">
          {isImage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={base} alt={name} className="h-auto max-h-[70vh] max-w-full" />
          ) : (
            <iframe src={base} title={name} sandbox="" className="h-[70vh] w-full" />
          )}
        </div>
      ) : null}
    </li>
  );
}

function MessageBody({ message }: { message: ThreadMessage }) {
  const t = useTranslations("Tickets.mailThread");
  const [showQuote, setShowQuote] = useState(false);
  const [asHtml, setAsHtml] = useState(Boolean(message.body_html));
  const { visible, quoted } = splitQuoted(message.body);
  return (
    <div className="flex min-w-0 flex-col gap-2">
      {asHtml && message.body_html ? (
        <SafeHtml html={message.body_html} className="rounded-md border border-border bg-surface p-3 text-sm" testId="ticket-mail-html" />
      ) : (
        <SafeText className="rounded-md border border-border bg-surface p-3 text-sm" testId="ticket-mail-text">
          {visible}
          {quoted && showQuote ? <span className="mt-2 block border-l-2 border-border pl-2 text-muted">{quoted}</span> : null}
        </SafeText>
      )}
      <div className="flex flex-wrap gap-2">
        {!asHtml && quoted ? (
          <button type="button" className={ui.buttonSm} onClick={() => setShowQuote((v) => !v)}>
            {showQuote ? t("hideQuote") : t("showQuote")}
          </button>
        ) : null}
        {message.body_html ? (
          <button type="button" className={ui.buttonSm} onClick={() => setAsHtml((v) => !v)}>
            {asHtml ? t("showText") : t("showHtml")}
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function TicketMailThread({
  ticketId,
  messages,
  canReply,
  onReply,
}: {
  ticketId: string;
  messages: ThreadMessage[];
  canReply: boolean;
  onReply?: (message: ThreadMessage) => void;
}) {
  const t = useTranslations("Tickets.mailThread");
  if (messages.length === 0) return <p className="text-sm text-muted">{t("empty")}</p>;
  return (
    <ol className="flex min-w-0 flex-col gap-3" data-testid="ticket-mail-thread">
      {messages.map((m) => {
        const status = displayStatus(m);
        const inbound = m.direction === "in";
        return (
          <li
            key={m.id}
            className={`${ui.card} flex min-w-0 flex-col gap-2 ${inbound ? "border-l-4 border-l-border" : "border-l-4 border-l-gold"}`}
            data-testid={`ticket-mail-${m.direction}`}
          >
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
              <div className="flex flex-wrap items-center gap-2">
                <span className={ui.badge}>{inbound ? t("directionIn") : t("directionOut")}</span>
                <span className={statusClass(status)} data-testid="ticket-mail-status">
                  {t(`status.${status}`)}
                </span>
              </div>
              <span>{formatDateTime(messageTime(m))}</span>
            </div>
            <SafeLine className="text-sm font-medium">{m.subject || t("noSubject")}</SafeLine>
            <div className="flex flex-col gap-0.5 text-xs text-muted">
              <SafeLine>
                {t("from")}: {inbound ? (m.from_address ?? "") : (m.mailbox_address ?? "")}
              </SafeLine>
              <SafeLine>
                {t("to")}: {inbound ? (m.mailbox_address ?? m.to_addresses.join(", ")) : m.to_addresses.join(", ")}
              </SafeLine>
              {m.cc_addresses.length > 0 ? (
                <SafeLine>
                  {t("cc")}: {m.cc_addresses.join(", ")}
                </SafeLine>
              ) : null}
            </div>
            {status === "failed" && m.send_error ? (
              <p role="alert" className={ui.alert}>
                {t("sendError")}: <SafeLine>{m.send_error}</SafeLine>
              </p>
            ) : null}
            {m.status === "draft" && m.rejection_note ? (
              <p className={ui.notice}>
                {t("rejected")}: <SafeLine>{m.rejection_note}</SafeLine>
              </p>
            ) : null}
            <MessageBody message={m} />
            {m.attachments.length > 0 ? (
              <div className="flex min-w-0 flex-col gap-1">
                <span className={ui.label}>{t("attachments")}</span>
                <ul className="flex flex-col gap-1">
                  {m.attachments.map((a) => (
                    <AttachmentRow key={a.document_id} ticketId={ticketId} messageId={m.id} direction={m.direction} attachment={a} />
                  ))}
                </ul>
              </div>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {canReply && onReply ? (
                <button type="button" className={ui.buttonSm} onClick={() => onReply(m)}>
                  {t("replyTo")}
                </button>
              ) : null}
              <Link href={`/mail?message=${m.id}`} className="text-xs text-muted hover:underline">
                {t("openMail")}
              </Link>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
