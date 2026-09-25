"use client";

import { useState } from "react";

import { useTranslations } from "next-intl";

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

  const recompute = async () => {
    setBusy(true);
    const res = await bff<Message>(`/api/bff/mail/messages/${message.id}/suggest`, { method: "POST" });
    setBusy(false);
    if (res.ok) onUpdated(res.data);
  };

  const sendReplyDraft = async () => {
    if (!message.suggestion.reply_draft) return;
    setBusy(true);
    const res = await bff<Message>(`/api/bff/mail/messages/${message.id}/reply-draft`, {
      method: "POST",
      body: JSON.stringify({ body: message.suggestion.reply_draft }),
    });
    setBusy(false);
    if (res.ok) onDraftCreated(res.data);
  };

  const applyPlaybook = async () => {
    if (!message.suggestion.playbook_id) return;
    setBusy(true);
    const res = await bff<Message>(`/api/bff/mail/messages/${message.id}/apply-playbook`, {
      method: "POST",
      body: JSON.stringify({ playbook_id: message.suggestion.playbook_id }),
    });
    setBusy(false);
    if (res.ok) onDraftCreated(res.data);
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
        </div>
      ) : null}
    </section>
  );
}
