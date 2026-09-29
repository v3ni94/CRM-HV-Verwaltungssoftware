"use client";

import { useState } from "react";

import { useTranslations } from "next-intl";

import { LexofficeInvoiceCopyChip } from "@/components/lexoffice/LexofficeInvoiceCopyChip";
import { TicketProcessBadge } from "@/components/tickets/TicketProcessBadge";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import type { Message } from "./MailWorkspace";

export function SuggestionCard({
  message,
  onUpdated,
  onDraftCreated,
}: {
  message: Message;
  onUpdated: (next: Message) => void;
  onDraftCreated: (next: Message) => void;
}) {
  const t = useTranslations("Mail.suggestion");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playbookFeedback, setPlaybookFeedback] = useState<boolean | null>(null);

  /** "Passt / passt nicht" on the suggested playbook (audit 29.09.2026): counters on the
   * playbook, shown in the knowledge base; nothing is activated or archived by it. */
  const ratePlaybook = async (helpful: boolean) => {
    if (!message.suggestion.playbook_id) return;
    setBusy(true);
    setError(null);
    const res = await bff<unknown>(`/api/bff/mail/playbooks/${message.suggestion.playbook_id}/feedback`, {
      method: "POST",
      body: JSON.stringify({ helpful }),
    });
    setBusy(false);
    if (res.ok) setPlaybookFeedback(helpful);
    else setError(res.message);
  };

  const recompute = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<Message>(`/api/bff/mail/messages/${message.id}/suggest`, { method: "POST" });
    setBusy(false);
    if (res.ok) onUpdated(res.data);
    else setError(res.message);
  };

  const sendReplyDraft = async () => {
    if (!message.suggestion.reply_draft) return;
    setBusy(true);
    setError(null);
    const res = await bff<Message>(`/api/bff/mail/messages/${message.id}/reply-draft`, {
      method: "POST",
      body: JSON.stringify({ body: message.suggestion.reply_draft }),
    });
    setBusy(false);
    if (res.ok) onDraftCreated(res.data);
    else setError(res.message);
  };

  const applyPlaybook = async () => {
    if (!message.suggestion.playbook_id) return;
    setBusy(true);
    setError(null);
    const res = await bff<Message>(`/api/bff/mail/messages/${message.id}/apply-playbook`, {
      method: "POST",
      body: JSON.stringify({ playbook_id: message.suggestion.playbook_id }),
    });
    setBusy(false);
    if (res.ok) onDraftCreated(res.data);
    else setError(res.message);
  };

  // Vorgangsart (Regel M19-11): KI-Vorschlag, sonst die Schlüsselworterkennung der
  // Klassifikation; Übernehmen legt bei Bedarf das Ticket an und wendet den Flow an.
  const keyword = (message.classification.process ?? null) as
    | { process_code?: string | null; confidence?: number | null; reason?: string | null }
    | null;
  const processCode = message.suggestion.process_code ?? keyword?.process_code ?? null;
  const processConfidence = message.suggestion.process_code
    ? (message.suggestion.process_confidence ?? null)
    : (keyword?.confidence ?? null);
  const processReason = message.suggestion.process_code
    ? (message.suggestion.process_reason ?? null)
    : (keyword?.reason ?? null);
  const [processDone, setProcessDone] = useState<string | null>(null);

  const applyProcess = async () => {
    if (!processCode) return;
    setBusy(true);
    setError(null);
    const res = await bff<{ ticket_id: string; number: number; applied: boolean }>(
      `/api/bff/mail/messages/${message.id}/apply-process`,
      { method: "POST", body: JSON.stringify({ process_code: processCode }) },
    );
    setBusy(false);
    if (res.ok) {
      setProcessDone(t("processApplied", { number: res.data.number }));
      onUpdated({ ...message, ticket_id: res.data.ticket_id });
    } else setError(res.message);
  };

  const status = message.suggestion_status;

  return (
    <section className={`${ui.card} flex flex-col gap-2 border border-border-soft`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{t("title")}</h3>
        <button type="button" className={ui.button} disabled={busy} onClick={() => void recompute()}>
          {t("recompute")}
        </button>
      </div>

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {processCode ? (
        <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="suggestion-process">
          <span>{t("process")}:</span>
          <TicketProcessBadge code={processCode} confidence={processConfidence} />
          {processReason ? <span className="text-muted">{processReason}</span> : null}
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void applyProcess()}>
            {t("applyProcess")}
          </button>
          {processDone ? <span className="text-muted">{processDone}</span> : null}
        </div>
      ) : null}
      <LexofficeInvoiceCopyChip
        messageId={message.id}
        ticketId={message.ticket_id}
        intent={message.suggestion.intent ?? null}
        invoiceNumber={message.suggestion.invoice_number ?? null}
      />
      {status === "none" || status === "pending" ? <p className="text-xs text-muted">{t(`status.${status}`)}</p> : null}
      {status === "failed" || status === "skipped" ? (
        <p className="text-xs text-muted">{t(`status.${status}`, { reason: message.suggestion.reason || "" })}</p>
      ) : null}

      {status === "ready" ? (
        <div className="flex flex-col gap-2 text-sm">
          <div className="flex flex-wrap gap-2 text-xs">
            {message.suggestion.category ? (
              <span className={ui.badge}>
                {t("category")}: {message.suggestion.category}
              </span>
            ) : null}
            {message.suggestion.urgency ? (
              <span className={ui.badge}>
                {t("urgency")}: {t(`urgencyLevel.${message.suggestion.urgency}`)}
              </span>
            ) : null}
            {message.suggestion.property_number ? (
              <span className={ui.badge}>
                {t("property")}: {message.suggestion.property_number}
              </span>
            ) : null}
            {message.suggestion.contact_name ? (
              <span className={ui.badge}>
                {t("contact")}: {message.suggestion.contact_name}
              </span>
            ) : null}
          </div>
          {message.suggestion.summary ? <p>{message.suggestion.summary}</p> : null}
          {message.suggestion.playbook_id ? (
            <p className="text-xs text-muted">
              {t("playbook")}
              {typeof message.suggestion.playbook_score === "number"
                ? ` (${t("playbookScore", { percent: Math.round(message.suggestion.playbook_score * 100) })})`
                : ""}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {message.suggestion.reply_draft ? (
              <button type="button" className={ui.button} disabled={busy} onClick={() => void sendReplyDraft()}>
                {t("sendReplyDraft")}
              </button>
            ) : null}
            {message.suggestion.playbook_id ? (
              <button type="button" className={ui.button} disabled={busy} onClick={() => void applyPlaybook()}>
                {t("applyPlaybook")}
              </button>
            ) : null}
          </div>
          {message.suggestion.playbook_id ? (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <button
                type="button"
                className={ui.buttonSm}
                aria-pressed={playbookFeedback === true}
                disabled={busy}
                onClick={() => void ratePlaybook(true)}
              >
                {t("playbookHelpful")}
              </button>
              <button
                type="button"
                className={ui.buttonSm}
                aria-pressed={playbookFeedback === false}
                disabled={busy}
                onClick={() => void ratePlaybook(false)}
              >
                {t("playbookUnhelpful")}
              </button>
              {playbookFeedback !== null ? <span className="text-muted">{t("feedbackSaved")}</span> : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
