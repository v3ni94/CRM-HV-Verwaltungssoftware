"use client";

import { useEffect, useRef, useState } from "react";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { AssignmentPrompt } from "@/components/assignment/AssignmentPrompt";
import { AttachmentReceiptAction } from "@/components/receipts/AttachmentReceiptAction";
import { ContactRoleBadges } from "@/components/common/ContactRoleBadges";
import { SafeText } from "@/components/ui/SafeText";
import { StatusChip } from "@/components/ui/StatusChip";
import { ui } from "@/lib/ui";

import { DraftEditor } from "./DraftEditor";
import type { Message } from "./MailWorkspace";
import { PreparationCard } from "./PreparationCard";
import { SuggestionCard } from "./SuggestionCard";

type Member = { user_id: string; display_name: string; email: string };
type SyncEvent = { id: string; occurred_at: string; type: string; payload: Record<string, unknown> };

function syncEventText(e: SyncEvent, t: ReturnType<typeof useTranslations>): string {
  const p = e.payload;
  if (e.type === "message.gmail_state_changed") {
    const effect = String(p.effect ?? "noted");
    return `${String(p.mailbox_address ?? "")}: ${String(p.from ?? "")} → ${String(p.to ?? "")} (${t(`copyBy.${String(p.by ?? "user")}`)}), ${t(`syncEvent.${effect}`)}`;
  }
  if (e.type === "message.completed") return t("syncEvent.completed", { source: String(p.source ?? "") });
  if (e.type === "message.reopened") return t("syncEvent.reopened_group", { source: String(p.source ?? "") });
  if (e.type === "message.gmail_restore_requested") return t("syncEvent.restore_requested");
  return e.type;
}

function submitterLabel(message: Message, members: Member[] | null, t: ReturnType<typeof useTranslations>): string {
  if (!message.submitted_by) return "";
  const member = members?.find((m) => m.user_id === message.submitted_by);
  const who = member?.display_name || member?.email || message.submitted_by;
  return message.submitted_at ? t("submittedBy", { who, at: formatDateTime(message.submitted_at) }) : who;
}

/** Von/An/Cc-Block (operator 27.09.2026): jede Zeile für sich, lange Empfängerlisten brechen
 * um; eigene Postfachadressen des Mandanten sind dezent gekennzeichnet. Gilt für ein- und
 * ausgehende Mails gleichermaßen. */
export function MailRecipients({ message, mailboxAddresses, className }: { message: Message; mailboxAddresses?: string[]; className?: string }) {
  const t = useTranslations("Mail");
  const own = new Set((mailboxAddresses ?? []).map((a) => a.toLowerCase()));
  const isOwn = (address: string) => own.has(address.toLowerCase());
  const addressList = (addresses: string[]) =>
    addresses.map((address, i) => (
      <span key={`${address}-${i}`} className="inline-flex items-center gap-1">
        <span>
          {address}
          {i < addresses.length - 1 ? "," : ""}
        </span>
        {isOwn(address) ? (
          <span className="rounded bg-subtle-bg px-1 text-[10px] text-subtle" title={t("ownMailboxHint")}>
            {t("ownMailbox")}
          </span>
        ) : null}
      </span>
    ));
  return (
    <div className={`flex min-w-0 flex-col gap-0.5 text-sm text-muted ${className ?? ""}`}>
      {message.from_address ? (
        <p className="min-w-0 break-words [overflow-wrap:anywhere]">
          <span className="text-subtle">{t("fromLabel")} </span>
          {addressList([message.from_address])}
        </p>
      ) : null}
      {message.to_addresses.length > 0 ? (
        <p className="min-w-0 flex-wrap break-words [overflow-wrap:anywhere]">
          <span className="text-subtle">{t("toLabel")} </span>
          {addressList(message.to_addresses)}
        </p>
      ) : null}
      {message.cc_addresses && message.cc_addresses.length > 0 ? (
        <p className="min-w-0 flex-wrap break-words [overflow-wrap:anywhere]">
          <span className="text-subtle">{t("ccLabel")} </span>
          {addressList(message.cc_addresses)}
        </p>
      ) : null}
    </div>
  );
}

function ThreadEntry({ message, mailboxAddresses }: { message: Message; mailboxAddresses?: string[] }) {
  const t = useTranslations("Mail");
  return (
    <li className={`${ui.card} flex min-w-0 flex-col gap-1.5`}>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span className={ui.badge}>{message.direction === "in" ? t("directionIn") : t("directionOut")}</span>
        <span>{formatDateTime(message.direction === "in" ? message.received_at : message.sent_at)}</span>
      </div>
      <p className="min-w-0 break-words text-sm font-medium [overflow-wrap:anywhere]">{message.subject || t("noSubject")}</p>
      <MailRecipients message={message} mailboxAddresses={mailboxAddresses} className="text-xs" />
      <SafeText className="text-sm">{message.body ?? message.body_preview}</SafeText>
    </li>
  );
}

type RejectedAttachment = { filename: string; mime: string; size: number; reason: string };

function rejectedAttachments(message: Message): RejectedAttachment[] {
  const value = message.classification?.attachments_rejected;
  return Array.isArray(value) ? (value as RejectedAttachment[]) : [];
}

function MailActionBar({
  position,
  busy,
  canCreateTicket,
  canMarkDone,
  onReply,
  onCreateTicket,
  onMarkDone,
}: {
  position: "top" | "bottom";
  busy: boolean;
  canCreateTicket: boolean;
  canMarkDone: boolean;
  onReply: () => void;
  onCreateTicket: () => void;
  onMarkDone: () => void;
}) {
  const t = useTranslations("Mail");
  const sticky = position === "top" ? "sticky top-0 z-10 -mx-1 border-b border-border-soft bg-surface/95 px-1 py-2 backdrop-blur" : "";
  return (
    <div
      className={`flex flex-wrap items-center gap-2 ${sticky}`}
      data-testid={`mail-actions-${position}`}
      role="toolbar"
      aria-label={t("actionsLabel")}
    >
      <button type="button" className={ui.button} disabled={busy} onClick={onReply}>
        {t("reply")}
      </button>
      {canCreateTicket ? (
        <button type="button" className={ui.button} disabled={busy} onClick={onCreateTicket}>
          {t("createTicket")}
        </button>
      ) : null}
      {canMarkDone ? (
        <button type="button" className={ui.button} disabled={busy} onClick={onMarkDone}>
          {t("markDone")}
        </button>
      ) : null}
    </div>
  );
}

export function MailDetail({
  message,
  canApprove,
  canReadMembers,
  mailboxAddresses,
  onUpdated,
  onCreated,
}: {
  message: Message | null;
  canApprove: boolean;
  canReadMembers: boolean;
  // Eigene Postfachadressen des Mandanten (operator 27.09.2026, Antworten mit An/Cc), um im
  // Von/An/Cc-Block zu kennzeichnen, welcher Empfänger ein eigenes Postfach ist.
  mailboxAddresses?: string[];
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
  // M20-04 Vier-Augen-Prinzip: Re-Authentifizierung vor der Freigabe (5 Minuten gültig).
  const [showReauth, setShowReauth] = useState(false);
  const [reauthPassword, setReauthPassword] = useState("");
  const [reauthTotp, setReauthTotp] = useState("");
  const [reauthError, setReauthError] = useState<string | null>(null);
  // Antwortentwurf zur ausgewählten Eingangsmail (operator 27.09.2026): "Vorbereiten" oder
  // "Antworten" legen ihn an, er wird direkt unter der Nachricht bearbeitet, statt nur still
  // im Reiter Entwürfe zu landen.
  const [replyDraft, setReplyDraft] = useState<Message | null>(null);
  const replyRef = useRef<HTMLDivElement | null>(null);
  // Rückkanal M20-08: Verlauf der Abgleichereignisse, auf Wunsch geladen.
  const [syncEvents, setSyncEvents] = useState<SyncEvent[] | null>(null);
  const [showSyncEvents, setShowSyncEvents] = useState(false);

  useEffect(() => {
    setThread(null);
    setError(null);
    setReplyDraft(null);
    setSyncEvents(null);
    setShowSyncEvents(false);
    setShowReject(false);
    setRejectNote("");
    setShowReauth(false);
    setReauthPassword("");
    setReauthTotp("");
    setReauthError(null);
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
  // List rows carry only a preview until the detail arrives (M3).
  const bodyLoaded = message.body !== undefined;
  const bodyText = bodyLoaded ? message.body : null;
  const rejected = rejectedAttachments(message);

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

  const showReplyDraft = (draft: Message) => {
    setReplyDraft(draft);
    // Der Editor steht unter der Nachricht; bei langen Mails dorthin springen.
    window.setTimeout(() => replyRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" }), 0);
  };
  const reply = async () => {
    if (replyDraft && replyDraft.status === "draft") {
      showReplyDraft(replyDraft);
      return;
    }
    // Review 1.36.0: no client side pick from the thread. Any open draft of the thread could be
    // a stale answer to an older mail or a colleague's draft. The server returns only the
    // caller's own open draft that replies to exactly this message, otherwise it creates one.
    const next = await act("/reply-draft", "POST", {});
    if (next) {
      showReplyDraft(next);
      onCreated(next);
    }
  };
  const onDraftCreated = (next: Message) => {
    showReplyDraft(next);
    onCreated(next);
  };
  const onReplyDraftUpdated = (next: Message) => {
    setReplyDraft(next);
    onUpdated(next);
  };
  const markDone = async () => {
    const next = await act("", "PATCH", { status: "done" });
    if (next) onUpdated(next);
  };
  // Manual catch up of the Gmail archive (operator 27.09.2026), idempotent on the server.
  const archiveNow = async () => {
    const next = await act("/archive", "POST");
    if (next) onUpdated(next);
  };
  // Rückkanal M20-08: zurück in den Gmail Posteingang, Automatik zurücknehmen, Verlauf.
  const restoreInbox = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ copies: number }>(`/api/bff/mail/messages/${message.id}/restore-inbox`, { method: "POST", body: "{}" });
    if (res.ok) {
      const fresh = await bff<Message>(`/api/bff/mail/messages/${message.id}`);
      if (fresh.ok) onUpdated(fresh.data);
    } else setError(res.message);
    setBusy(false);
  };
  const revertDecision = async () => {
    if (!window.confirm(t("revertConfirm"))) return;
    setBusy(true);
    setError(null);
    const res = await bff<{ message_reopened: boolean }>(`/api/bff/mail/messages/${message.id}/revert-gmail-decision`, {
      method: "POST",
      body: "{}",
    });
    if (res.ok) {
      const fresh = await bff<Message>(`/api/bff/mail/messages/${message.id}`);
      if (fresh.ok) onUpdated(fresh.data);
    } else setError(res.message);
    setBusy(false);
  };
  const toggleSyncEvents = async () => {
    const next = !showSyncEvents;
    setShowSyncEvents(next);
    if (next && syncEvents === null) {
      const res = await bff<SyncEvent[]>(`/api/bff/mail/messages/${message.id}/sync-events`);
      setSyncEvents(res.ok ? res.data : []);
    }
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
    setBusy(true);
    setError(null);
    const res = await bff<Message>(`/api/bff/mail/messages/${message.id}/approve`, { method: "POST" });
    setBusy(false);
    if (res.ok) {
      onUpdated(res.data);
      return;
    }
    if (res.problem?.code === "MHVP-COMM-0002") {
      // M20-04: kein oder abgelaufener Re-Auth-Nachweis, Dialog statt Fehlermeldung.
      setShowReauth(true);
      return;
    }
    setError(res.message);
  };
  const confirmReauthAndApprove = async () => {
    setBusy(true);
    setReauthError(null);
    const body =
      reauthTotp.trim().length > 0 ? { totp_code: reauthTotp.trim() } : { password: reauthPassword };
    const reauth = await bff<{ method: string }>("/api/bff/mail/mail-approval/reauth", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (!reauth.ok) {
      setBusy(false);
      setReauthError(reauth.message);
      return;
    }
    setReauthPassword("");
    setReauthTotp("");
    setBusy(false);
    setShowReauth(false);
    await approve();
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
  // TNR#<nummer> im Betreff eines nicht am Ticket beteiligten Absenders: nur Vorschlag,
  // keine automatische Zuordnung (Review 26.09.2026, H5).
  const tnrSuggestion = message.classification?.tnr_suggestion as { ticket_id: string; number: number } | undefined;
  const reject = async () => {
    if (!rejectNote.trim()) return;
    const next = await act("/reject", "POST", { note: rejectNote.trim() });
    if (next) {
      onUpdated(next);
      setShowReject(false);
      setRejectNote("");
    }
  };

  // Gemeinsame Aktionsleiste oben (sticky) und unten (Betreiberauftrag 26.09.2026).
  const showActions = bodyLoaded && !["draft", "sending", "pending", "sent"].includes(message.status);
  const actionBar = (position: "top" | "bottom") => (
    <MailActionBar
      position={position}
      busy={busy}
      canCreateTicket={!message.ticket_id}
      canMarkDone={message.status !== "done"}
      onReply={() => void reply()}
      onCreateTicket={() => void createTicket()}
      onMarkDone={() => void markDone()}
    />
  );

  return (
    <div className={`${ui.card} flex min-w-0 flex-col gap-4`}>
      <div className="flex min-w-0 flex-col gap-1 border-b border-border-soft pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h2 className="min-w-0 break-words text-lg font-semibold [overflow-wrap:anywhere]">{message.subject || t("noSubject")}</h2>
          <span className={`${ui.badge} shrink-0`}>{t(`status.${message.status}`)}</span>
        </div>
        <MailRecipients message={message} mailboxAddresses={mailboxAddresses} />
        <div className="flex flex-wrap gap-3 text-xs text-subtle">
          {message.ticket_id ? (
            <Link href={`/tickets/${message.ticket_id}`} className="hover:underline">
              {t("openTicket")}
            </Link>
          ) : null}
          {message.contact_id ? (
            <span className="inline-flex flex-wrap items-center gap-1.5">
              <Link href={`/kontakte/${message.contact_id}`} className="hover:underline">
                {t("openContact")}
              </Link>
              <ContactRoleBadges contactId={message.contact_id} />
            </span>
          ) : null}
          {message.property_id ? (
            <Link href={`/objekte/${message.property_id}`} className="hover:underline">
              {t("openProperty")}
            </Link>
          ) : null}
          {message.attachment_document_ids.length > 0 ? <span>{t("attachments", { count: message.attachment_document_ids.length })}</span> : null}
        </div>
        {message.direction === "in" && message.archive_status ? (
          <p
            className={`text-xs ${["failed", "scope_missing"].includes(message.archive_status) ? "text-warning-fg" : "text-subtle"}`}
            data-testid="mail-archive-status"
          >
            {t(`archiveStatus.${message.archive_status}`, {
              at: message.archived_at ? formatDateTime(message.archived_at) : message.archive_attempted_at ? formatDateTime(message.archive_attempted_at) : "",
            })}
            {message.archive_error && message.archive_status !== "archived" ? ` (${message.archive_error})` : ""}
            {["failed", "scope_missing", "pending"].includes(message.archive_status) ? (
              <>
                {" "}
                <button type="button" className="underline" disabled={busy} onClick={() => void archiveNow()}>
                  {t("archiveRetry")}
                </button>
              </>
            ) : null}
          </p>
        ) : null}
        {message.direction === "in" && message.gmail_sync && message.gmail_sync.state !== "aus" ? (
          <div className="flex flex-col gap-1 text-xs text-subtle" data-testid="mail-gmail-state">
            <div className="flex flex-wrap items-center gap-2">
              <StatusChip domain="mailSync" status={message.gmail_sync.state} label={t(`sync.${message.gmail_sync.state}`)} />
              {message.done_source === "gmail" ? <span className={ui.badge}>{t("doneFromGmailShort")}</span> : null}
            </div>
            <ul className="flex flex-col gap-0.5">
              {message.gmail_sync.copies.map((c, i) => (
                <li key={c.message_id ?? `${c.mailbox_address}-${i}`}>
                  {c.visible
                    ? `${t(`copyState.${c.gmail_state ?? "inbox"}`, {
                        address: c.mailbox_address ?? "",
                        by: t(`copyBy.${c.gmail_state_by ?? "user"}`),
                        at: c.gmail_state_at ? formatDateTime(c.gmail_state_at) : "",
                      })}${c.authoritative ? ` (${t("copyAuthoritative")})` : ""}`
                    : t("copyHidden", { address: c.mailbox_address ?? "" })}
                </li>
              ))}
            </ul>
            {message.gmail_keep_open_label ? <p>{t("keepOpenLabel", { label: message.gmail_keep_open_label })}</p> : null}
            {message.gmail_settle_until ? <p>{t("settlePending", { until: formatDateTime(message.gmail_settle_until) })}</p> : null}
            <div className="flex flex-wrap gap-3">
              {message.gmail_sync.copies.some((c) => c.visible && ["archived", "trashed"].includes(c.gmail_state ?? "")) ? (
                <button type="button" className="underline" disabled={busy} onClick={() => void restoreInbox()}>
                  {t("restoreInbox")}
                </button>
              ) : null}
              {message.done_source === "gmail" ? (
                <button type="button" className="underline" disabled={busy} onClick={() => void revertDecision()}>
                  {t("revertDecision")}
                </button>
              ) : null}
              <button type="button" className="underline" onClick={() => void toggleSyncEvents()} aria-expanded={showSyncEvents}>
                {t("syncEvents")}
              </button>
            </div>
            {showSyncEvents ? (
              <ul className="flex flex-col gap-0.5" data-testid="mail-sync-events">
                {(syncEvents ?? []).map((e) => (
                  <li key={e.id}>
                    {formatDateTime(e.occurred_at)} · {syncEventText(e, t)}
                  </li>
                ))}
                {syncEvents && syncEvents.length === 0 ? <li>{t("syncEventsEmpty")}</li> : null}
              </ul>
            ) : null}
          </div>
        ) : null}
        {rejected.length > 0 ? (
          <p className="text-xs text-warning-fg" data-testid="mail-attachments-rejected">
            {t("attachmentsRejected", { list: rejected.map((r) => `${r.filename} (${r.reason})`).join(", ") })}
          </p>
        ) : null}
        {message.direction === "in" && message.attachment_document_ids.length > 0 ? (
          <ul className="flex flex-wrap gap-2">
            {message.attachment_document_ids.map((attachmentId, i) => (
              <li key={attachmentId}>
                <AttachmentReceiptAction messageId={message.id} documentId={attachmentId} label={t("attachmentInvoice", { number: i + 1 })} />
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      {showActions ? actionBar("top") : null}

      {message.direction === "in" && tnrSuggestion ? (
        <p className={ui.notice} data-testid="mail-tnr-suggestion">
          {t("tnrSuggestion", { number: String(tnrSuggestion.number) })}{" "}
          <Link href={`/tickets/${tnrSuggestion.ticket_id}`} className="font-medium text-fg hover:underline">
            {t("openTicket")}
          </Link>
        </p>
      ) : null}
      {message.direction === "in" ? (
        <AssignmentPrompt
          entityType="message"
          entityId={message.id}
          canDecide
          onDecided={() => {
            void bff<Message>(`/api/bff/mail/messages/${message.id}`).then((res) => {
              if (res.ok) onUpdated(res.data);
            });
          }}
        />
      ) : null}
      {message.direction === "in" ? <SuggestionCard message={message} onUpdated={onUpdated} onDraftCreated={onDraftCreated} /> : null}
      {message.direction === "in" ? <PreparationCard message={message} onDraftCreated={onDraftCreated} /> : null}

      {message.direction === "in" && invoiceForward?.decision === "suggest" && !forwarded ? (
        <div className={`${ui.card} flex flex-wrap items-center justify-between gap-2`}>
          <span className="text-sm">{invoiceForward.reason}</span>
          <button type="button" className={ui.button} disabled={busy} onClick={() => void forwardInvoice()}>
            {ts("forwardInvoice")}
          </button>
        </div>
      ) : null}
      {forwarded ? <p className="text-xs text-success-fg">{ts("forwardInvoiceDone")}</p> : null}

      {!bodyLoaded ? (
        <p className="text-sm text-muted">{t("loadingDetail")}</p>
      ) : message.status === "draft" ? (
        <DraftEditor key={message.id} message={message} onUpdated={onUpdated} />
      ) : message.status === "sending" ? (
        <div className="flex flex-col gap-3">
          <p className={ui.notice} data-testid="mail-sending-hint">
            {t("sendingHint")}
          </p>
          <SafeText className="rounded-md border border-border bg-surface-2 p-3 text-sm" testId="mail-body">{bodyText}</SafeText>
          {canApprove ? (
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className={ui.primary} disabled={busy} onClick={() => void approve()}>
                {t("approveAndSend")}
              </button>
              <button type="button" className={ui.danger} disabled={busy} onClick={() => setShowReject((v) => !v)}>
                {t("reject")}
              </button>
            </div>
          ) : null}
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
      ) : message.status === "pending" ? (
        <div className="flex flex-col gap-3">
          <p className="text-xs text-muted">{submitterLabel(message, members, t)}</p>
          <SafeText className="rounded-md border border-border bg-surface-2 p-3 text-sm" testId="mail-body">{bodyText}</SafeText>
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
          <SafeText className="rounded-md border border-border bg-surface-2 p-3 text-sm" testId="mail-body">{bodyText}</SafeText>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <SafeText className="rounded-md border border-border bg-surface-2 p-3 text-sm" testId="mail-body">{bodyText}</SafeText>
          {actionBar("bottom")}
        </div>
      )}

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}

      {message.direction === "in" && replyDraft ? (
        <section ref={replyRef} className="flex flex-col gap-2 border-t border-border-soft pt-3" data-testid="mail-reply-draft">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{t("replyDraftTitle")}</h3>
            <span className={ui.badge}>{t(`status.${replyDraft.status}`)}</span>
          </div>
          {replyDraft.status === "draft" ? (
            <DraftEditor key={replyDraft.id} message={replyDraft} onUpdated={onReplyDraftUpdated} />
          ) : (
            <p className={ui.notice} data-testid="mail-reply-draft-status">
              {replyDraft.status === "pending" ? t("replyDraftSubmitted") : t("replyDraftClosed")}
            </p>
          )}
        </section>
      ) : null}

      {showReauth ? (
        <div className={`${ui.card} flex flex-col gap-2`} data-testid="mail-reauth-dialog">
          <h3 className="text-sm font-semibold">{t("reauth.title")}</h3>
          <p className="text-xs text-muted">{t("reauth.hint")}</p>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("reauth.passwordLabel")}</span>
            <input
              type="password"
              className={ui.input}
              value={reauthPassword}
              onChange={(e) => setReauthPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("reauth.totpLabel")}</span>
            <input
              type="text"
              inputMode="numeric"
              className={ui.input}
              value={reauthTotp}
              onChange={(e) => setReauthTotp(e.target.value)}
            />
          </label>
          {reauthError ? (
            <p role="alert" className={ui.alert}>
              {reauthError}
            </p>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className={ui.primary}
              disabled={busy || (!reauthPassword && !reauthTotp)}
              onClick={() => void confirmReauthAndApprove()}
            >
              {t("reauth.confirm")}
            </button>
            <button
              type="button"
              className={ui.button}
              disabled={busy}
              onClick={() => {
                setShowReauth(false);
                setReauthPassword("");
                setReauthTotp("");
                setReauthError(null);
              }}
            >
              {t("reauth.cancel")}
            </button>
          </div>
        </div>
      ) : null}

      {thread && thread.length > 1 ? (
        <section className="flex flex-col gap-2 border-t border-border-soft pt-3">
          <h3 className="text-sm font-semibold">{t("thread")}</h3>
          <ul className="flex flex-col gap-2">
            {thread.map((entry) => (
              <ThreadEntry key={entry.id} message={entry} mailboxAddresses={mailboxAddresses} />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
