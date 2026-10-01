"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState, type FormEvent } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type LetterTemplate = { id: string; code: string; name: string; subject: string; body: string; version: number; active: boolean };
type ContactItem = { id: string; display_name: string };

/** Placeholders the template may use (``mhvp.documents.letters``); shown as a hint. */
export const PLACEHOLDER_HINT = "{{ empfaenger.anrede }}, {{ empfaenger.name }}, {{ objekt.name }}, {{ felder.betreff }}, {{ felder.text }}";

/** Body of POST /letters and /letters/preview (single) or /letters/serial (several). */
export function letterBody(templateId: string, contacts: ContactItem[], subject: string, text: string) {
  const fields: Record<string, string> = {};
  if (subject.trim()) fields.betreff = subject.trim();
  if (text.trim()) fields.text = text.trim();
  if (contacts.length === 1) return { template_id: templateId, contact_id: contacts[0]!.id, fields };
  return { template_id: templateId, contact_ids: contacts.map((c) => c.id), fields };
}

/** Letter templates and letters (11.3, M6-01): manage templates with versions, create a letter
 *  from a template with a PDF preview, or a serial letter for several recipients. Generated
 *  letters are filed and linked; nothing is sent. */
export function LetterTemplates({ templates: initial, canManage }: { templates: LetterTemplate[]; canManage: boolean }) {
  const t = useTranslations("LetterTemplates");
  const [templates, setTemplates] = useState(initial);
  const [form, setForm] = useState({ code: "", name: "", subject: "", body: "" });
  const [templateId, setTemplateId] = useState(initial[0]?.id ?? "");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<ContactItem[]>([]);
  const [recipients, setRecipients] = useState<ContactItem[]>([]);
  const [subject, setSubject] = useState("");
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (query.trim().length < 2) {
      setHits([]);
      return;
    }
    let active = true;
    const timer = setTimeout(async () => {
      const res = await bff<{ items?: ContactItem[] } | ContactItem[]>(`/api/bff/contacts?q=${encodeURIComponent(query.trim())}&page_size=10`);
      if (!active || !res.ok) return;
      setHits(Array.isArray(res.data) ? res.data : (res.data.items ?? []));
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  function pick(template: LetterTemplate) {
    setForm({ code: template.code, name: template.name, subject: template.subject, body: template.body });
  }

  async function saveTemplate(e: FormEvent) {
    e.preventDefault();
    const res = await bff<LetterTemplate>("/api/bff/document-templates", { method: "POST", body: JSON.stringify(form) });
    if (res.ok) {
      setTemplates((all) => [...all.filter((x) => x.code !== res.data.code), res.data]);
      setTemplateId(res.data.id);
      setMessage({ ok: true, text: t("templateSaved", { version: res.data.version }) });
    } else setMessage({ ok: false, text: res.message });
  }

  async function showPreview() {
    if (!templateId || recipients.length === 0) return;
    setBusy(true);
    const body = letterBody(templateId, recipients.slice(0, 1), subject, text);
    try {
      const res = await fetch("/api/bff/letters/preview", {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) setPreview(URL.createObjectURL(await res.blob()));
      else setMessage({ ok: false, text: t("previewFailed") });
    } catch {
      setMessage({ ok: false, text: t("previewFailed") });
    }
    setBusy(false);
  }

  async function create() {
    if (!templateId || recipients.length === 0) return;
    setBusy(true);
    const serial = recipients.length > 1;
    const res = await bff<{ id?: string; documents?: { id: string }[] }>(serial ? "/api/bff/letters/serial" : "/api/bff/letters", {
      method: "POST",
      body: JSON.stringify(letterBody(templateId, recipients, subject, text)),
    });
    setBusy(false);
    if (res.ok) setMessage({ ok: true, text: t("created", { count: serial ? (res.data.documents?.length ?? 0) : 1 }) });
    else setMessage({ ok: false, text: res.message });
  }

  return (
    <div className="flex flex-col gap-6">
      {message ? (
        <p role="status" className={message.ok ? ui.success : ui.alert}>
          {message.text}
        </p>
      ) : null}
      <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("letterTitle")}>
        <h2 className="text-base font-semibold">{t("letterTitle")}</h2>
        <label className={ui.label}>
          {t("template")}
          <select className={ui.input} value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
            {templates.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name} (v{x.version})
              </option>
            ))}
          </select>
        </label>
        <label className={ui.label}>
          {t("recipientSearch")}
          <input className={ui.input} value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        {hits.length > 0 ? (
          <ul className="flex flex-wrap gap-2">
            {hits.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  className={ui.buttonSm}
                  disabled={recipients.some((r) => r.id === c.id)}
                  onClick={() => setRecipients((all) => [...all, c])}
                >
                  {c.display_name}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <div>
          <p className={ui.label}>{t("recipients", { count: recipients.length })}</p>
          <ul className="flex flex-wrap gap-2">
            {recipients.map((c) => (
              <li key={c.id}>
                <button type="button" className={ui.buttonSm} aria-label={t("remove", { name: c.display_name })} onClick={() => setRecipients((all) => all.filter((r) => r.id !== c.id))}>
                  {c.display_name} ×
                </button>
              </li>
            ))}
          </ul>
        </div>
        <label className={ui.label}>
          {t("subject")}
          <input className={ui.input} value={subject} onChange={(e) => setSubject(e.target.value)} />
        </label>
        <label className={ui.label}>
          {t("text")}
          <textarea className={ui.input} rows={6} value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        <p className={ui.help}>{t("serialHint")}</p>
        <div className={ui.formActions}>
          <button type="button" className={ui.secondary} disabled={busy || recipients.length === 0} onClick={() => void showPreview()}>
            {t("preview")}
          </button>
          <button type="button" className={ui.primary} disabled={busy || recipients.length === 0} onClick={() => void create()}>
            {recipients.length > 1 ? t("createSerial") : t("create")}
          </button>
        </div>
        {preview ? <iframe title={t("previewTitle")} src={preview} className="h-[32rem] w-full rounded-md border border-border" /> : null}
      </section>
      {canManage ? (
        <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("templatesTitle")}>
          <h2 className="text-base font-semibold">{t("templatesTitle")}</h2>
          <ul className="flex flex-wrap gap-2">
            {templates.map((x) => (
              <li key={x.id}>
                <button type="button" className={ui.buttonSm} onClick={() => pick(x)}>
                  {x.name} (v{x.version})
                </button>
              </li>
            ))}
          </ul>
          <form onSubmit={saveTemplate} className="grid gap-2 sm:grid-cols-2">
            <label className={ui.label}>
              {t("code")}
              <input className={ui.input} required pattern="[a-z0-9_]{2,63}" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
            </label>
            <label className={ui.label}>
              {t("name")}
              <input className={ui.input} required maxLength={200} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className={`${ui.label} sm:col-span-2`}>
              {t("templateSubject")}
              <input className={ui.input} required value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} />
            </label>
            <label className={`${ui.label} sm:col-span-2`}>
              {t("templateBody")}
              <textarea className={ui.input} required rows={8} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
            </label>
            <p className={`${ui.help} sm:col-span-2`}>{t("placeholders", { list: PLACEHOLDER_HINT })}</p>
            <div>
              <button type="submit" className={ui.primary}>
                {t("saveTemplate")}
              </button>
            </div>
          </form>
        </section>
      ) : null}
    </div>
  );
}
