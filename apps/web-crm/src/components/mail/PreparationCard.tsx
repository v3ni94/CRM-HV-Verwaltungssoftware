"use client";

import { useState } from "react";

import { useTranslations } from "next-intl";

import type { Preparation } from "@/lib/ai";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import type { Message } from "./MailWorkspace";

/** Mail-Vorbereitung (Welle 3 Punkt 14, M33): löst Kontakt, Einheit, Objekt und Rolle des
 * Absenders auf, sucht passende Dokumente je Objekt und schlägt einen Antwortentwurf vor. Nur
 * Vorschlag; „Übernehmen" öffnet den bestehenden Antwortentwurf-Fluss, nichts wird automatisch
 * versendet (Regel 0.1.6). */
export function PreparationCard({
  message,
  onDraftCreated,
}: {
  message: Message;
  onDraftCreated: (next: Message) => void;
}) {
  const t = useTranslations("Mail.preparation");
  const [preparation, setPreparation] = useState<Preparation | null>(message.suggestion.preparation ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [correcting, setCorrecting] = useState(false);
  const [note, setNote] = useState("");

  const compute = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<Preparation>(`/api/bff/mail/messages/${message.id}/preparation`, { method: "POST" });
    setBusy(false);
    if (res.ok) setPreparation(res.data);
    else setError(res.message);
  };

  const apply = async () => {
    if (!preparation?.draft) return;
    setBusy(true);
    const res = await bff<Message>(`/api/bff/mail/messages/${message.id}/reply-draft`, {
      method: "POST",
      body: JSON.stringify({ body: preparation.draft }),
    });
    setBusy(false);
    if (res.ok) onDraftCreated(res.data);
  };

  const correct = async () => {
    if (!note.trim()) return;
    setBusy(true);
    setError(null);
    const res = await bff<{ knowledge_entry_id: string }>(`/api/bff/mail/messages/${message.id}/preparation/correct`, {
      method: "POST",
      body: JSON.stringify({
        contact_id: preparation?.contact_id ?? null,
        unit_id: preparation?.unit_id ?? null,
        property_id: preparation?.property_id ?? null,
        note,
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setCorrecting(false);
    setNote("");
    await compute();
  };

  if (message.direction !== "in") return null;

  return (
    <section className={`${ui.card} flex flex-col gap-2 border border-border-soft`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{t("title")}</h3>
        <button type="button" className={ui.button} disabled={busy} onClick={() => void compute()}>
          {preparation ? t("recompute") : t("compute")}
        </button>
      </div>

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}

      {preparation ? (
        <div className="flex flex-col gap-2 text-sm">
          <div className="flex flex-wrap gap-2 text-xs">
            <span className={ui.badge}>
              {t("role")}: {preparation.role ? t(`roleValue.${preparation.role}`) : t("roleUnknown")}
            </span>
            {preparation.status !== "ready" ? <span className={ui.badge}>{t(`status.${preparation.status}`)}</span> : null}
          </div>

          {preparation.documents.length > 0 ? (
            <div className="flex flex-col gap-1">
              <span className={ui.label}>{t("documents")}</span>
              <ul className="list-inside list-disc text-xs text-muted">
                {preparation.documents.map((d, i) => (
                  <li key={`${d.source}-${d.ref ?? d.document_id ?? i}`}>
                    {d.title} <span className="text-subtle">({t(`documentSource.${d.source}`)})</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {preparation.draft ? (
            <div className="flex flex-col gap-1">
              <span className={ui.label}>{t("draft")}</span>
              <p className="whitespace-pre-wrap rounded-md border border-border bg-surface p-2 text-sm">{preparation.draft}</p>
            </div>
          ) : null}

          <ul className="list-inside list-disc text-xs text-subtle">
            {preparation.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>

          <div className={ui.formActions}>
            {preparation.draft ? (
              <button type="button" className={`${ui.primary} ${ui.actionFull}`} disabled={busy} onClick={() => void apply()}>
                {t("apply")}
              </button>
            ) : null}
            <button
              type="button"
              className={`${ui.button} ${ui.actionFull}`}
              disabled={busy}
              onClick={() => setCorrecting((v) => !v)}
            >
              {t("correct")}
            </button>
          </div>

          {correcting ? (
            <div className="flex flex-col gap-2 border-t border-border pt-2">
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("correctionNote")}</span>
                <textarea className={`${ui.input} min-h-20`} value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
              <button type="button" className={`${ui.primary} ${ui.actionFull}`} disabled={busy || !note.trim()} onClick={() => void correct()}>
                {t("correctionSave")}
              </button>
            </div>
          ) : null}

          {preparation.correction ? (
            <p className="text-xs text-muted">
              {t("correctionRecorded")}: {preparation.correction.note}
            </p>
          ) : null}
        </div>
      ) : (
        <p className="text-xs text-muted">{t("empty")}</p>
      )}
    </section>
  );
}
