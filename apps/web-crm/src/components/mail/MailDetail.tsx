"use client";

import { useEffect, useState } from "react";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

import { DraftEditor } from "./DraftEditor";
import type { Message } from "./MailWorkspace";
import { PreparationCard } from "./PreparationCard";
import { SuggestionCard } from "./SuggestionCard";

type Member = { user_id: string; display_name: string; email: string };

function submitterLabel(message: Message, members: Member[] | null, t: ReturnType<typeof useTranslations>): string {
  if (!message.submitted_by) return "";
  const member = members?.find((m) => m.user_id === message.submitted_by);
  const who = member?.display_name || member?.email || message.submitted_by;
  return message.submitted_at ? t("submittedBy", { who, at: formatDateTime(message.submitted_at) }) : who;
}

/** "Als Rechnung erfassen" on one attachment (M14): starts extract_invoice and links to the
 * review form in the invoices area; the invoice itself is created only there, after review. */
function AttachmentInvoiceAction({ messageId, attachmentId, label }: { messageId: string; attachmentId: string; label: string }) {
  const t = useTranslations("Mail");
  const [busy, setBusy] = useState(false);
  const [proposalId, setProposalId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ run_id: string; proposal_id: string | null }>(
      `/api/bff/mail/messages/${messageId}/attachments/${attachmentId}/invoice-extraction`,
      { method: "POST" },
    );
    setBusy(false);
    if (!res.ok) {
      setError(t("invoiceExtractionFailed", { reason: res.message }));
      return;
    }
    setProposalId(res.data.proposal_id);
  };

  if (proposalId) {
    return (
      <Link href={`/rechnungen?proposal=${proposalId}`} className="text-xs font-medium text-accent hover:underline">
        {t("openInvoiceReview")}
      </Link>
    );
  }

  return (
    <span className="flex flex-col gap-1">
      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void start()}>
        {label}: {t("captureAsInvoice")}
      </button>
      {error ? <span className="text-xs text-danger-fg">{error}</span> : null}
    </span>
  );
}

function ThreadEntry({ message }: { message: Message }) {
  const t = useTranslations("Mail");
  return (
    <li className={`${ui.card} flex min-w-0 flex-col gap-1.5`}>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span className={ui.badge}>{message.direction === "in" ? t("directionIn") : t("directionOut")}</span>
        <span>{formatDateTime(message.direction === "in" ? message.received_at : message.sent_at)}</span>
      </div>
      <p className="break-words text-sm font-medium">{message.subject || t("noSubject")}</p>
      <p className="whitespace-pre-wrap break-words text-sm">{message.body}</p>
    </li>
  );
}

export function MailDetail({
  message,
  canApprove,
  canReadMembers,
  onUpdated,
  onCreated,
}: {
  message: Message | null;
  canApprove: boolean;
  canReadMembers: boolean;
  onUpdated: (next: Message) => void;
  onCreated: (next: Message) => void;
}) {
  const t = useTranslations("Mail");
  const ts = useTranslations("MailSettings");
  const router = useRouter();
  const [forwarded, setForwarded] = useState(false);
  const [thread, setThread] = useState<Message[] | null>(null);
  const [members, setMembers] = useState<Member[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejectNote, setRejectNote] = useState("");
  const [showReject, setShowReject] = useState(false);

  useEffect(() => {
    setThread(null);
    setError(null);
    setShowReject(false);
    setRejectNote("");
    if (!message) return;
    void bff<Message[]>(`/api/bff/mail/messages/${message.id}/thread`).then((res) => {
      if (res.ok) setThread(res.data);
    });
    // Only the selected message's id should retrigger the thread fetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [message?.id]);

  useEffect(() => {
    if (!canReadMembers || members) return;
    void bff<Member[]>("/api/bff/tenant/members").then((res) => {
      if (res.ok) setMembers(res.data);
    });
  }, [canReadMembers, members]);

  if (!message) return <p className="text-sm text-muted">{t("selectMessage")}</p>;

  const act = async (path: string, method: string, body?: unknown) => {
    setBusy(true);
    setError(null);
    const res = await bff<Message>(`/api/bff/mail/messages/${message.id}${path}`, {
      method,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    setBusy(false);
    if (res.ok) return res.data;
    setError(res.message);
    return null;
  };

  const reply = async () => {
    const next = await act("/reply-draft", "POST", {});
    if (next) onCreated(next);
  };
  const markDone = async () => {
    const next = await act("", "PATCH", { status: "done" });
    if (next) onUpdated(next);
  };
  const createTicket = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ id: string }>(`/api/bff/mail/messages/${message.id}/ticket`, { method: "POST" });
    setBusy(false);
    if (res.ok) router.push(`/tickets/${res.data.id}`);
    else setError(res.message);
  };
  const approve = async () => {
    const next = await act("/approve", "POST");
    if (next) onUpdated(next);
  };
  const forwardInvoice = async () => {
    if (!window.confirm(ts("forwardInvoiceConfirm"))) return;
    setBusy(true);
    setError(null);
    const res = await bff<{ forwarded_to: string }>(`/api/bff/mail/messages/${message.id}/forward-invoice`, {
      method: "POST",
    });
    setBusy(false);
    if (res.ok) setForwarded(true);
    else setError(res.message);
  };
  const invoiceForward = message.classification?.invoice_forward as
    | { decision: string; reason: string }
    | undefined;
  const reject = async () => {
    if (!rejectNote.trim()) return;
    const next = await act("/reject", "POST", { note: rejectNote.trim() });
    if (next) {
      onUpdated(next);
      setShowReject(false);
      setRejectNote("");
    }
  };

  return (
    <div className={`${ui.card} flex min-w-0 flex-col gap-4`}>
      <div className="flex min-w-0 flex-col gap-1 border-b border-border-soft pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h2 className="min-w-0 break-words text-lg font-semibold">{message.subject || t("noSubject")}</h2>
          <span className={`${ui.badge} shrink-0`}>{t(`status.${message.status}`)}</span>
        </div>
        <p className="break-words text-sm text-muted">
          {message.direction === "in" ? t("from", { address: message.from_address ?? "" }) : t("toField", { address: message.to_addresses.join(", ") })}
        </p>
        <div className="flex flex-wrap gap-3 text-xs text-subtle">
          {message.ticket_id ? (
            <Link href={`/tickets/${message.ticket_id}`} className="hover:underline">
              {t("openTicket")}
            </Link>
          ) : null}
          {message.contact_id ? (
            <Link href={`/kontakte/${message.contact_id}`} className="hover:underline">
              {t("openContact")}
            </Link>
          ) : null}
          {message.property_id ? (
            <Link href={`/objekte/${message.property_id}`} className="hover:underline">
              {t("openProperty")}
            </Link>
          ) : null}
          {message.attachment_document_ids.length > 0 ? <span>{t("attachments", { count: message.attachment_document_ids.length })}</span> : null}
        </div>
        {message.direction === "in" && message.attachment_document_ids.length > 0 ? (
          <ul className="flex flex-wrap gap-2">
            {message.attachment_document_ids.map((attachmentId, i) => (
              <li key={attachmentId}>
                <AttachmentInvoiceAction messageId={message.id} attachmentId={attachmentId} label={t("attachmentInvoice", { number: i + 1 })} />
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      {message.direction === "in" ? <SuggestionCard message={message} onUpdated={onUpdated} onDraftCreated={onCreated} /> : null}
      {message.direction === "in" ? <PreparationCard message={message} onDraftCreated={onCreated} /> : null}

      {message.direction === "in" && invoiceForward?.decision === "suggest" && !forwarded ? (
        <div className={`${ui.card} flex flex-wrap items-center justify-between gap-2`}>
          <span className="text-sm">{invoiceForward.reason}</span>
          <button type="button" className={ui.button} disabled={busy} onClick={() => void forwardInvoice()}>
            {ts("forwardInvoice")}
          </button>
        </div>
      ) : null}
      {forwarded ? <p className="text-xs text-success-fg">{ts("forwardInvoiceDone")}</p> : null}

      {message.status === "draft" ? (
        <DraftEditor message={message} onUpdated={onUpdated} />
      ) : message.status === "pending" ? (
        <div className="flex flex-col gap-3">
          <p className="text-xs text-muted">{submitterLabel(message, members, t)}</p>
          <p className="whitespace-pre-wrap break-words rounded-md border border-border bg-surface p-3 text-sm">{message.body}</p>
          {canApprove ? (
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className={ui.primary} disabled={busy} onClick={() => void approve()}>
                {t("approveAndSend")}
              </button>
              <button type="button" className={ui.danger} disabled={busy} onClick={() => setShowReject((v) => !v)}>
                {t("reject")}
              </button>
            </div>
          ) : (
            <p className="text-xs text-muted">{t("pendingHint")}</p>
          )}
          {showReject ? (
            <div className="flex flex-col gap-2">
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("rejectionNoteLabel")}</span>
                <textarea className={ui.input} rows={3} value={rejectNote} onChange={(e) => setRejectNote(e.target.value)} />
              </label>
              <button type="button" className={ui.button} disabled={busy || !rejectNote.trim()} onClick={() => void reject()}>
                {t("confirmReject")}
              </button>
            </div>
          ) : null}
        </div>
      ) : message.status === "sent" ? (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-muted">{message.sent_at ? t("sentAt", { at: formatDateTime(message.sent_at) }) : ""}</p>
          <p className="whitespace-pre-wrap break-words rounded-md border border-border bg-surface p-3 text-sm">{message.body}</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="whitespace-pre-wrap break-words rounded-md border border-border bg-surface p-3 text-sm">{message.body}</p>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={ui.button} disabled={busy} onClick={() => void reply()}>
              {t("reply")}
            </button>
            {!message.ticket_id ? (
              <button type="button" className={ui.button} disabled={busy} onClick={() => void createTicket()}>
                {t("createTicket")}
              </button>
            ) : null}
            {message.status !== "done" ? (
              <button type="button" className={ui.button} disabled={busy} onClick={() => void markDone()}>
                {t("markDone")}
              </button>
            ) : null}
          </div>
        </div>
      )}

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}

      {thread && thread.length > 1 ? (
        <section className="flex flex-col gap-2 border-t border-border-soft pt-3">
          <h3 className="text-sm font-semibold">{t("thread")}</h3>
          <ul className="flex flex-col gap-2">
            {thread.map((entry) => (
              <ThreadEntry key={entry.id} message={entry} />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
