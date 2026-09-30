"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import type { ChatMessage } from "@/components/portal/types";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Chat mit der Verwaltung zur Meldung (M21-01): Nachrichten sind externe Kommentare der
 *  Meldung, der Verlauf bleibt im Vorgang. Antworten der Verwaltung erscheinen hier und als
 *  Benachrichtigung. Kein Notdienst: der Hinweis wird immer gezeigt. */
export function PortalChat({ ticketId }: { ticketId: string }) {
  const t = useTranslations("Tickets");
  const format = useFormatter();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const result = await bff<ChatMessage[]>(`/api/bff/portal/tickets/${ticketId}/messages`);
    if (result.ok) setMessages(result.data);
    else setError(result.message);
  }, [ticketId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!body.trim()) return;
    setBusy(true);
    const result = await bff<ChatMessage>(`/api/bff/portal/tickets/${ticketId}/messages`, {
      method: "POST",
      body: JSON.stringify({ body: body.trim() }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setBody("");
    await load();
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="chat-title" data-testid="portal-chat">
      <h2 id="chat-title" className={ui.h2}>
        {t("chatTitle")}
      </h2>
      <p className={ui.help}>{t("chatNote")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {messages.length === 0 ? (
        <p className="text-sm text-muted">{t("chatEmpty")}</p>
      ) : (
        <ul className="flex flex-col gap-2" aria-live="polite">
          {messages.map((m) => (
            <li key={m.id} className="whitespace-pre-wrap break-words rounded-md border border-border bg-surface-2 px-3 py-2 text-sm">
              <span className="block text-xs text-subtle">
                {m.direction === "own" ? t("chatOwn") : t("chatManagement")},{" "}
                {format.dateTime(new Date(m.created_at), { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}
              </span>
              {m.body}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={onSubmit} noValidate aria-busy={busy} className="flex flex-col gap-2">
        <label htmlFor="chat-body" className={ui.label}>
          {t("chatField")}
        </label>
        <textarea id="chat-body" rows={3} maxLength={5000} className={ui.input} value={body} onChange={(e) => setBody(e.target.value)} />
        <button type="submit" className={`${ui.button} ${ui.actionFull}`} disabled={busy}>
          {t("chatSend")}
        </button>
      </form>
    </section>
  );
}
