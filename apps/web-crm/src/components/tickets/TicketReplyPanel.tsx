"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { SafeLine } from "@/components/ui/SafeText";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type ReplyTemplate = { id: string; name: string; topic: string | null };
type Attachment = { document_id: string; title: string | null; filename: string | null; missing: boolean };
type Preview = {
  template_id: string;
  template_name: string;
  subject: string;
  body: string;
  to_addresses: string[];
  mailbox_id: string | null;
  mailbox_address: string | null;
  can_send: boolean;
  attachments: Attachment[];
};
type SentMessage = { id: string; status: string };

const PLACEHOLDER_RE = /\{[a-zA-Z_]+\}/;

/** Antwortvorlage im Ticket (operator 26.09.2026): Vorlage wählen, Vorschau mit ausgefüllten
 *  Platzhaltern und Anhängen, bearbeiten, dann "Antwort senden". Der Versand geht über den
 *  bestehenden Antwortweg des Tickets (Postfach des Tickets, Freigabe) und nur nach Klick. */
export function TicketReplyPanel({ ticketId, canSend }: { ticketId: string; canSend: boolean }) {
  const t = useTranslations("Tickets.reply");
  const [templates, setTemplates] = useState<ReplyTemplate[] | null>(null);
  const [templateId, setTemplateId] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [to, setTo] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<SentMessage | null>(null);

  useEffect(() => {
    let cancelled = false;
    void bff<ReplyTemplate[]>("/api/bff/tickets/reply-templates?active=true").then((res) => {
      if (!cancelled) setTemplates(res.ok ? res.data : []);
    });
    return () => {
      cancelled = true;
    };
  }, []);

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
    setTo(res.data.to_addresses.join(", "));
    setAttachments(res.data.attachments.filter((a) => !a.missing));
  }

  async function send() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    const res = await bff<SentMessage>(`/api/bff/tickets/${ticketId}/reply`, {
      method: "POST",
      body: JSON.stringify({
        template_id: preview.template_id,
        subject: subject.trim(),
        body,
        to_addresses: to
          .split(",")
          .map((a) => a.trim())
          .filter(Boolean),
        attachment_document_ids: attachments.map((a) => a.document_id),
        confirm: true,
      }),
    });
    setBusy(false);
    if (res.ok) {
      setSent(res.data);
      setPreview(null);
      setTemplateId("");
    } else {
      setError(res.message);
    }
  }

  const openPlaceholders = PLACEHOLDER_RE.test(subject) || PLACEHOLDER_RE.test(body);
  const noRecipient = to.trim().length === 0;

  return (
    <section className={`${ui.card} flex min-w-0 flex-col gap-3`} data-testid="ticket-reply-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{t("title")}</h2>
        <Link href="/einstellungen/antwortvorlagen" className="text-xs text-muted hover:underline">
          {t("manage")}
        </Link>
      </div>
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
        <div className="flex min-w-0 flex-col gap-3" data-testid="ticket-reply-preview">
          <p className="text-xs text-muted">{t("preview")}</p>
          <p className="text-xs text-muted">
            {t("mailbox")}: <SafeLine>{preview.mailbox_address ?? ""}</SafeLine>
          </p>
          {!preview.can_send ? (
            <p role="alert" className={ui.alert}>
              {t("noMailbox")}
            </p>
          ) : null}
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("to")}</span>
            <input className={ui.input} value={to} onChange={(e) => setTo(e.target.value)} />
          </label>
          {noRecipient ? <p className="text-xs text-danger-fg">{t("noRecipient")}</p> : null}
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("subject")}</span>
            <input className={ui.input} value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={998} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("body")}</span>
            <textarea className={`${ui.input} min-w-0 max-w-full`} rows={10} value={body} onChange={(e) => setBody(e.target.value)} />
          </label>
          {openPlaceholders ? <p className="text-xs text-danger-fg">{t("openPlaceholders")}</p> : null}
          <div className="flex min-w-0 flex-col gap-1">
            <span className={ui.label}>{t("attachments")}</span>
            {attachments.length === 0 ? (
              <p className="text-xs text-muted">{t("noAttachments")}</p>
            ) : (
              <ul className="flex flex-col gap-1" data-testid="ticket-reply-attachments">
                {attachments.map((a) => (
                  <li key={a.document_id} className="flex min-w-0 items-center justify-between gap-2 text-sm">
                    <SafeLine className="truncate">{a.title || a.filename || a.document_id}</SafeLine>
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
            {preview.attachments.some((a) => a.missing) ? <p className="text-xs text-danger-fg">{t("attachmentMissing")}</p> : null}
          </div>
          <p className="text-xs text-muted">{t("sendHint")}</p>
          {canSend ? (
            <button
              type="button"
              className={`${ui.primary} w-fit`}
              disabled={busy || !preview.can_send || openPlaceholders || noRecipient || !subject.trim() || !body.trim()}
              onClick={() => void send()}
            >
              {t("send")}
            </button>
          ) : null}
        </div>
      ) : null}
      {sent ? (
        <p className={ui.success} data-testid="ticket-reply-sent">
          {t("sent")}{" "}
          <Link href="/mail" className="font-medium hover:underline">
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
