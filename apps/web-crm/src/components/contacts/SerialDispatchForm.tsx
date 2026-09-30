"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { ContactPicker, type PickedContact } from "@/components/hoa/ContactPicker";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { CHANNELS } from "./DispatchPanel";

/** Serienbrief je Zustellweg (M23-03): Vorlage mit Platzhaltern wird je Empfänger zu einem
 *  eigenen Dokument zusammengeführt und mit einer Zustellung je Zustellweg vorbereitet.
 *  Vertreterregel gilt wie im Einzelbrief; ein Fehler bricht den gesamten Lauf ab. */
export type SerialResult = {
  batch: string;
  counts: Record<string, number>;
  by_channel: Record<string, { id: string; contact_id: string }[]>;
};

export function SerialDispatchForm({
  templates,
}: {
  templates: { id: string; name: string }[];
}) {
  const t = useTranslations("Dispatch");
  const [templateId, setTemplateId] = useState(templates[0]?.id ?? "");
  const [channel, setChannel] = useState<"" | (typeof CHANNELS)[number]>("");
  const [subject, setSubject] = useState("");
  const [text, setText] = useState("");
  const [recipients, setRecipients] = useState<PickedContact[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SerialResult | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    setResult(null);
    const res = await bff<SerialResult>("/api/bff/dispatches/serial-merge", {
      method: "POST",
      body: JSON.stringify({
        template_id: templateId,
        contact_ids: recipients.map((r) => r.id),
        ...(channel ? { channel } : {}),
        fields: { betreff: subject, text },
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setResult(res.data);
  }

  return (
    <div className="flex flex-col gap-3">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("template")}</span>
        <select className={ui.input} value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
          {templates.map((tpl) => (
            <option key={tpl.id} value={tpl.id}>
              {tpl.name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("subject")}</span>
        <input className={ui.input} value={subject} onChange={(e) => setSubject(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("text")}</span>
        <textarea className={ui.input} rows={5} value={text} onChange={(e) => setText(e.target.value)} />
        <span className={ui.help}>{t("placeholderHint")}</span>
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("channelOrPreferred")}</span>
        <select
          className={ui.input}
          value={channel}
          onChange={(e) => setChannel(e.target.value as "" | (typeof CHANNELS)[number])}
        >
          <option value="">{t("preferred")}</option>
          {CHANNELS.map((c) => (
            <option key={c} value={c}>
              {t(`channels.${c}`)}
            </option>
          ))}
        </select>
      </label>
      <ContactPicker
        label={t("addRecipient")}
        onPick={(c) => setRecipients((r) => (r.some((x) => x.id === c.id) ? r : [...r, c]))}
      />
      {recipients.length > 0 ? (
        <ul className="flex flex-wrap gap-2">
          {recipients.map((r) => (
            <li key={r.id} className={ui.badge}>
              {r.display_name}
              <button
                type="button"
                className="ml-2"
                aria-label={t("remove", { name: r.display_name })}
                onClick={() => setRecipients((all) => all.filter((x) => x.id !== r.id))}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">{t("noRecipients")}</p>
      )}
      <div>
        <button
          type="button"
          className={ui.primary}
          disabled={busy || !templateId || recipients.length === 0 || !text.trim()}
          onClick={() => void run()}
        >
          {t("runSerial")}
        </button>
      </div>
      {result ? (
        <section aria-live="polite" className={ui.card}>
          <h3 className="text-sm font-semibold">{t("result", { batch: result.batch })}</h3>
          <ul className="mt-1 text-sm">
            {CHANNELS.filter((c) => (result.counts[c] ?? 0) > 0).map((c) => (
              <li key={c}>{t("resultLine", { channel: t(`channels.${c}`), count: result.counts[c] ?? 0 })}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
