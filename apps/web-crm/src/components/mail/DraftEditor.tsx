"use client";

import { useState } from "react";

import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import type { Message } from "./MailWorkspace";

export function DraftEditor({ message, onUpdated }: { message: Message; onUpdated: (next: Message) => void }) {
  const t = useTranslations("Mail");
  const [to, setTo] = useState(message.to_addresses.join(", "));
  const [subject, setSubject] = useState(message.subject ?? "");
  const [body, setBody] = useState(message.body ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<Message>(`/api/bff/mail/messages/${message.id}/draft`, {
      method: "PATCH",
      body: JSON.stringify({
        subject: subject.trim(),
        body,
        to_addresses: to
          .split(",")
          .map((a) => a.trim())
          .filter(Boolean),
      }),
    });
    setBusy(false);
    if (res.ok) onUpdated(res.data);
    else setError(res.message);
    return res.ok;
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    if (!(await save())) {
      setBusy(false);
      return;
    }
    const res = await bff<Message>(`/api/bff/mail/messages/${message.id}/submit`, { method: "POST" });
    setBusy(false);
    if (res.ok) onUpdated(res.data);
    else setError(res.message);
  };

  return (
    <div className="flex flex-col gap-3">
      {message.rejection_note ? <p className={ui.notice}>{t("rejectionNote", { note: message.rejection_note })}</p> : null}
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("to")}</span>
        <input className={ui.input} value={to} onChange={(e) => setTo(e.target.value)} disabled={busy} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("subject")}</span>
        <input className={ui.input} value={subject} onChange={(e) => setSubject(e.target.value)} disabled={busy} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("body")}</span>
        <textarea className={ui.input} rows={10} value={body} onChange={(e) => setBody(e.target.value)} disabled={busy} />
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={ui.button} disabled={busy} onClick={() => void save()}>
          {t("save")}
        </button>
        <button type="button" className={ui.primary} disabled={busy || !to.trim() || !body.trim()} onClick={() => void submit()}>
          {t("submitForApproval")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
