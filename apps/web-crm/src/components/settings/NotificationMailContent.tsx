"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Mode = "voll" | "hinweis";

/** Mandantenschalter für den Inhalt der Benachrichtigungsmails (U15-04, Datenschutz):
 *  `voll` (Standard) sendet Titel und Text, `hinweis` nur Anzahl und Link ins CRM.
 *  GET und PATCH /tenant/settings (Feld notification_mail_content). Ohne Leserecht auf die
 *  Mandanteneinstellungen bleibt der Abschnitt ausgeblendet. */
export function NotificationMailContent() {
  const t = useTranslations("NotificationSettings.mailContent");
  const [mode, setMode] = useState<Mode | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const res = await bff<{ notification_mail_content?: Mode }>("/api/bff/tenant/settings");
      if (res.ok) setMode(res.data.notification_mail_content === "hinweis" ? "hinweis" : "voll");
    })();
  }, []);

  async function change(next: Mode) {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ notification_mail_content: Mode }>("/api/bff/tenant/settings", {
      method: "PATCH",
      body: JSON.stringify({ notification_mail_content: next }),
    });
    setBusy(false);
    if (res.ok) {
      setMode(res.data.notification_mail_content);
      setMessage(t("saved"));
    } else setError(res.message);
  }

  if (mode === null) return null;
  return (
    <section className={ui.card} aria-labelledby="notification-mail-content-title">
      <div className="flex flex-col gap-3">
        <h2 id="notification-mail-content-title" className={ui.h2}>
          {t("title")}
        </h2>
        <p className={ui.help}>{t("description")}</p>
        {(["voll", "hinweis"] as const).map((m) => (
          <label key={m} className="flex items-center gap-2 text-sm">
            <input type="radio" name="notification-mail-content" checked={mode === m} disabled={busy} onChange={() => void change(m)} data-testid={`notification-mail-content-${m}`} />
            <span>{t(m === "voll" ? "full" : "hint")}</span>
          </label>
        ))}
        {message ? <span className="text-xs text-success-fg">{message}</span> : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
