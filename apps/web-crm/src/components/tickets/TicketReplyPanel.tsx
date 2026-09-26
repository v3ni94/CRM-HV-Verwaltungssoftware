"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { SafeLine } from "@/components/ui/SafeText";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { formatBytes, isValidAddress, parseAddressList } from "@/lib/mailText";
import { ui } from "@/lib/ui";

type ReplyTemplate = { id: string; name: string; topic: string | null };
export type ReplyAttachment = { document_id: string; title: string | null; filename: string | null; missing: boolean; size?: number | null };
type ReplyContext = {
  reply_to_message_id: string | null;
  subject: string;
  to_addresses: string[];
  cc_addresses: string[];
  unverified_sender: string | null;
  mailbox_id: string | null;
  mailbox_address: string | null;
  can_send: boolean;
  tnr: string;
};
type Preview = ReplyContext & {
  template_id: string;
  template_name: string;
  body: string;
  attachments: ReplyAttachment[];
};
type SentMessage = { id: string; status: string };
type DocumentHit = { document_id: string; title: string; filename: string; mime_type: string; size: number };

/** Target of the reply chosen in the thread ("Auf diese Mail antworten"). */
export type ReplyTarget = { messageId: string; at: string | null };

const PLACEHOLDER_RE = /\{[a-zA-Z_]+\}/;

/** Antwortformular im Ticket (operator 26.09.2026): An und Kopie aus der Ursprungsmail
 *  vorbelegt (nur beteiligte Absender), Betreff mit Kennung TNR#<nummer>, Text frei oder aus
 *  einer Antwortvorlage, eigene Anhänge aus Dokumenten oder Upload. Die Antwort geht als
 *  eingereichter Entwurf in den Postausgang und wird erst nach der Vier-Augen-Freigabe über
 *  das Postfach des Tickets versendet. Es wird nichts ohne Klick angelegt. */
export function TicketReplyPanel({
  ticketId,
  canSend,
  target,
  onSent,
}: {
  ticketId: string;
  canSend: boolean;
  target?: ReplyTarget | null;
  onSent?: (message: SentMessage) => void;
}) {
  const t = useTranslations("Tickets.reply");
  const [templates, setTemplates] = useState<ReplyTemplate[] | null>(null);
  const [templateId, setTemplateId] = useState("");
  const [context, setContext] = useState<ReplyContext | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [to, setTo] = useState("");
  const [cc, setCc] = useState("");
  const [attachments, setAttachments] = useState<ReplyAttachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<SentMessage | null>(null);
  const [docQuery, setDocQuery] = useState("");
  const [docHits, setDocHits] = useState<DocumentHit[] | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    void bff<ReplyTemplate[]>("/api/bff/tickets/reply-templates?active=true").then((res) => {
      if (!cancelled) setTemplates(res.ok ? res.data : []);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Vorbelegung (An, Kopie, Betreff, Postfach) je Antwortziel; ohne Ziel die letzte Eingangsmail.
  useEffect(() => {
    let cancelled = false;
    const query = target?.messageId ? `?reply_to_message_id=${encodeURIComponent(target.messageId)}` : "";
    setSent(null);
    setError(null);
    void bff<ReplyContext>(`/api/bff/tickets/${ticketId}/reply-context${query}`).then((res) => {
      if (cancelled) return;
      if (!res.ok) {
        setContext(null);
        setError(t("loadFailed"));
        return;
      }
      setContext(res.data);
      setTo(res.data.to_addresses.join(", "));
      setCc(res.data.cc_addresses.join(", "));
      setSubject((prev) => (prev.trim() && !target ? prev : res.data.subject));
    });
    return () => {
      cancelled = true;
    };
    // Only the ticket and the chosen target message retrigger the context load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketId, target?.messageId]);

  async function choose(id: string) {
    setTemplateId(id);
    setSent(null);
    setError(null);
    if (!id) {
      setPreview(null);
      return;
    }
    setBusy(true);
    const res = await bff<Preview>(`/api/bff/tickets/${ticketId}/reply-templates/${id}/preview`);
    setBusy(false);
    if (!res.ok) {
      setPreview(null);
      setError(t("loadFailed"));
      return;
    }
    setPreview(res.data);
    setSubject(res.data.subject);
    setBody(res.data.body);
    if (res.data.to_addresses.length > 0) setTo(res.data.to_addresses.join(", "));
    setAttachments((prev) => {
      const known = new Set(prev.map((a) => a.document_id));
      return [...prev, ...res.data.attachments.filter((a) => !a.missing && !known.has(a.document_id))];
    });
  }

  async function searchDocuments() {
    const q = docQuery.trim();
    if (q.length < 2) return;
    const res = await bff<DocumentHit[]>(`/api/bff/tickets/${ticketId}/reply-documents?q=${encodeURIComponent(q)}`);
    setDocHits(res.ok ? res.data : []);
  }

  function addDocument(hit: DocumentHit) {
    setAttachments((prev) =>
      prev.some((a) => a.document_id === hit.document_id)
        ? prev
        : [...prev, { document_id: hit.document_id, title: hit.title, filename: hit.filename, missing: false, size: hit.size }],
    );
  }

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch("/api/bff/documents", { method: "POST", body: form });
      const data = (await res.json()) as { id?: string; title?: string; filename?: string; size?: number };
      if (!res.ok || !data.id) throw new Error("upload");
      setAttachments((prev) => [...prev, { document_id: String(data.id), title: data.title ?? file.name, filename: data.filename ?? file.name, missing: false, size: data.size ?? file.size }]);
    } catch {
      setError(t("uploadFailed"));
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  const toList = parseAddressList(to);
  const ccList = parseAddressList(cc);
  const invalid = [...toList, ...ccList].find((a) => !isValidAddress(a));
  const openPlaceholders = PLACEHOLDER_RE.test(subject) || PLACEHOLDER_RE.test(body);
  const noRecipient = toList.length === 0;
  const canSubmit = Boolean(context?.can_send) && !busy && !uploading && !openPlaceholders && !noRecipient && !invalid && subject.trim().length > 0 && body.trim().length > 0;

  async function send() {
    if (!canSubmit || !context) return;
    setBusy(true);
    setError(null);
    const res = await bff<SentMessage>(`/api/bff/tickets/${ticketId}/reply`, {
      method: "POST",
      body: JSON.stringify({
        template_id: preview?.template_id ?? null,
        subject: subject.trim(),
        body,
        to_addresses: toList,
        cc_addresses: ccList,
        reply_to_message_id: context.reply_to_message_id,
        attachment_document_ids: attachments.map((a) => a.document_id),
        confirm: true,
      }),
    });
    setBusy(false);
    if (res.ok) {
      setSent(res.data);
      setPreview(null);
      setTemplateId("");
      setBody("");
      setAttachments([]);
      onSent?.(res.data);
    } else {
      setError(res.message);
    }
  }

  function reset() {
    setPreview(null);
    setTemplateId("");
    setBody("");
    setAttachments([]);
    setError(null);
    if (context) {
      setTo(context.to_addresses.join(", "));
      setCc(context.cc_addresses.join(", "));
      setSubject(context.subject);
    }
  }

  return (
    <section className={`${ui.card} flex min-w-0 flex-col gap-3`} data-testid="ticket-reply-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{t("title")}</h2>
        <Link href="/einstellungen/antwortvorlagen" className="text-xs text-muted hover:underline">
          {t("manage")}
        </Link>
      </div>
      <p className="text-xs text-muted" data-testid="ticket-reply-target">
        {target?.at ? t("replyingTo", { at: formatDateTime(target.at) }) : t("replyingToLatest")}
      </p>
      {templates && templates.length === 0 ? (
        <p className="text-sm text-muted">{t("emptyTemplates")}</p>
      ) : (
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("select")}</span>
          <select className={ui.input} value={templateId} disabled={!templates || busy} onChange={(e) => void choose(e.target.value)}>
            <option value="">{t("none")}</option>
            {(templates ?? []).map((tpl) => (
              <option key={tpl.id} value={tpl.id}>
                {tpl.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {preview ? (
        <p className="text-xs text-muted" data-testid="ticket-reply-preview">
          {t("preview")}
        </p>
      ) : null}
      {context ? (
        <div className="flex min-w-0 flex-col gap-3" data-testid="ticket-reply-form">
          <p className="text-xs text-muted">
            {t("mailbox")}: <SafeLine>{context.mailbox_address ?? ""}</SafeLine>
          </p>
          {!context.can_send ? (
            <p role="alert" className={ui.alert}>
              {t("noMailbox")}
            </p>
          ) : null}
          {context.unverified_sender ? (
            <p className={ui.notice} data-testid="ticket-reply-unverified">
              {t("unverifiedSender", { address: context.unverified_sender })}{" "}
              <button type="button" className={ui.buttonSm} onClick={() => setTo(context.unverified_sender ?? "")}>
                {t("useSender")}
              </button>
            </p>
          ) : null}
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("to")}</span>
            <input className={ui.input} value={to} onChange={(e) => setTo(e.target.value)} />
          </label>
          {noRecipient ? <p className="text-xs text-danger-fg">{t("noRecipient")}</p> : null}
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("cc")}</span>
            <input className={ui.input} value={cc} onChange={(e) => setCc(e.target.value)} />
          </label>
          {invalid ? <p className="text-xs text-danger-fg">{t("invalidAddress", { address: invalid })}</p> : null}
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("subject")}</span>
            <input className={ui.input} value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={998} />
          </label>
          <p className={ui.help}>{t("tnrHint", { tnr: context.tnr })}</p>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("body")}</span>
            <textarea className={`${ui.input} min-w-0 max-w-full`} rows={10} value={body} onChange={(e) => setBody(e.target.value)} />
          </label>
          {openPlaceholders ? <p className="text-xs text-danger-fg">{t("openPlaceholders")}</p> : null}
          <div className="flex min-w-0 flex-col gap-2">
            <span className={ui.label}>{t("attachments")}</span>
            {attachments.length === 0 ? (
              <p className="text-xs text-muted">{t("noAttachments")}</p>
            ) : (
              <ul className="flex flex-col gap-1" data-testid="ticket-reply-attachments">
                {attachments.map((a) => (
                  <li key={a.document_id} className="flex min-w-0 items-center justify-between gap-2 text-sm">
                    <SafeLine className="truncate">
                      {a.title || a.filename || a.document_id}
                      {a.size ? <span className="text-xs text-muted"> ({formatBytes(a.size)})</span> : null}
                    </SafeLine>
                    <button
                      type="button"
                      className={ui.buttonSm}
                      aria-label={`${t("removeAttachment")}: ${a.title || a.filename || a.document_id}`}
                      onClick={() => setAttachments((prev) => prev.filter((x) => x.document_id !== a.document_id))}
                    >
                      {t("removeAttachment")}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {preview?.attachments.some((a) => a.missing) ? <p className="text-xs text-danger-fg">{t("attachmentMissing")}</p> : null}
            <div className="flex flex-wrap items-end gap-2">
              <label className="flex min-w-0 flex-col gap-1">
                <span className={ui.label}>{t("searchDocuments")}</span>
                <input
                  className={ui.input}
                  value={docQuery}
                  placeholder={t("searchPlaceholder")}
                  onChange={(e) => setDocQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void searchDocuments();
                    }
                  }}
                />
              </label>
              <button type="button" className={ui.buttonSm} disabled={docQuery.trim().length < 2} onClick={() => void searchDocuments()}>
                {t("searchDocuments")}
              </button>
              <label className={ui.buttonSm}>
                {uploading ? t("uploading") : t("upload")}
                <input
                  ref={fileInput}
                  type="file"
                  className="sr-only"
                  aria-label={t("upload")}
                  disabled={uploading}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void upload(file);
                  }}
                />
              </label>
            </div>
            {docHits ? (
              docHits.length === 0 ? (
                <p className="text-xs text-muted">{t("noDocumentsFound")}</p>
              ) : (
                <ul className="flex flex-col gap-1 text-sm" data-testid="ticket-reply-document-hits">
                  {docHits.map((hit) => (
                    <li key={hit.document_id} className="flex min-w-0 items-center justify-between gap-2">
                      <SafeLine className="truncate">
                        {hit.title || hit.filename} <span className="text-xs text-muted">({formatBytes(hit.size)})</span>
                      </SafeLine>
                      <button type="button" className={ui.buttonSm} onClick={() => addDocument(hit)} aria-label={`${t("addDocument")}: ${hit.title || hit.filename}`}>
                        {t("addDocument")}
                      </button>
                    </li>
                  ))}
                </ul>
              )
            ) : null}
          </div>
          <p className="text-xs text-muted">{t("approvalHint")}</p>
          <div className="flex flex-wrap gap-2">
            {canSend ? (
              <button type="button" className={ui.primary} disabled={!canSubmit} onClick={() => void send()}>
                {t("send")}
              </button>
            ) : null}
            <button type="button" className={ui.button} disabled={busy} onClick={reset}>
              {t("reset")}
            </button>
          </div>
        </div>
      ) : null}
      {sent ? (
        <p className={ui.success} data-testid="ticket-reply-sent">
          {t("sent")}{" "}
          <Link href={`/mail?message=${sent.id}`} className="font-medium hover:underline">
            {t("openMail")}
          </Link>
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
