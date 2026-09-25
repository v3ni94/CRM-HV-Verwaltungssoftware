"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export function TicketComments({ ticketId, comments }: { ticketId: string; comments: string[] }) {
  const t = useTranslations("Tickets");
  const router = useRouter();
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!body.trim()) return;
    setBusy(true);
    const result = await bff<{ id: string }>(`/api/bff/portal/tickets/${ticketId}/comments`, {
      method: "POST",
      body: JSON.stringify({ body: body.trim() }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setBody("");
    setSent(true);
    router.refresh();
  }

  return (
    <div className={`${ui.card} flex flex-col gap-3`}>
      <h2 className={ui.h2}>{t("history")}</h2>
      {comments.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {comments.map((c, i) => (
            <li key={i} className="rounded-md border border-border bg-surface px-3 py-2 text-sm">
              {c}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-2">
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {sent ? <p className={ui.success}>{t("commentSent")}</p> : null}
        <label htmlFor="comment-body" className={ui.label}>
          {t("commentField")}
        </label>
        <textarea id="comment-body" rows={3} className={ui.input} value={body} onChange={(e) => setBody(e.target.value)} />
        <button type="submit" className={`${ui.button} ${ui.actionFull}`} disabled={busy}>
          {t("commentSubmit")}
        </button>
      </form>
    </div>
  );
}
