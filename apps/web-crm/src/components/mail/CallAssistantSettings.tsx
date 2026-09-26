"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type CallAssistant = {
  enabled: boolean;
  sender_patterns: string[];
  keywords: string[];
};

function split(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/** Telefonassistenz Hallo Heidi (26.09.2026): Erkennungsmuster der Gesprächsprotokoll-Mails je
 *  Mandant. Erkannte Mails werden am Ticket ausgewertet (Anrufer, Objekt, Einheit, Anliegen);
 *  eine neue Rufnummer ergibt den Vorschlag "Stammdaten ergänzen" mit Antwortentwurf. */
export function CallAssistantSettings({ initial }: { initial: CallAssistant }) {
  const t = useTranslations("MailSettings");
  const [enabled, setEnabled] = useState(initial.enabled);
  const [senders, setSenders] = useState(initial.sender_patterns.join(", "));
  const [keywords, setKeywords] = useState(initial.keywords.join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    const res = await bff<CallAssistant>("/api/bff/mail/call-assistant", {
      method: "PUT",
      body: JSON.stringify({ enabled, sender_patterns: split(senders), keywords: split(keywords) }),
    });
    setBusy(false);
    if (res.ok) {
      setSenders(res.data.sender_patterns.join(", "));
      setKeywords(res.data.keywords.join(", "));
      setSaved(true);
    } else {
      setError(res.message);
    }
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`} data-testid="call-assistant-settings">
      <h2 className="text-sm font-semibold">{t("callAssistantTitle")}</h2>
      <p className="text-xs text-muted">{t("callAssistantHint")}</p>
      <label className="flex items-center gap-1.5 text-sm">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        {t("callAssistantEnabled")}
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("callAssistantSenders")}</span>
        <input className={ui.input} value={senders} onChange={(e) => setSenders(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("callAssistantKeywords")}</span>
        <input className={ui.input} value={keywords} onChange={(e) => setKeywords(e.target.value)} />
        <span className="text-xs text-muted">{t("callAssistantDefaultsHint")}</span>
      </label>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="flex items-center gap-3">
        <button type="button" className={ui.primary} disabled={busy} onClick={() => void save()}>
          {t("save")}
        </button>
        {saved ? <span className="text-xs text-success-fg">{t("saved")}</span> : null}
      </div>
    </section>
  );
}
