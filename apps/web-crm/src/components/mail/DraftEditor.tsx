"use client";

import { useEffect, useRef, useState } from "react";

import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import type { Message } from "./MailWorkspace";

/** Anhang am Entwurf (GET/POST/DELETE /mail/messages/{id}/attachments). */
export type DraftAttachment = {
  document_id: string;
  title: string;
  filename: string;
  mime_type: string;
  size: number;
};

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

function splitAddresses(value: string): string[] {
  return value
    .split(/[,;]/)
    .map((a) => a.trim())
    .filter(Boolean);
}

/** The editable fields of a draft as the inputs show them. */
type DraftFields = { to: string; cc: string; subject: string; body: string };

function draftFields(message: Message): DraftFields {
  return {
    to: message.to_addresses.join(", "),
    cc: ((message as { cc_addresses?: string[] }).cc_addresses ?? []).join(", "),
    subject: message.subject ?? "",
    body: message.body ?? "",
  };
}

function sameFields(a: DraftFields, b: DraftFields): boolean {
  return a.to === b.to && a.cc === b.cc && a.subject === b.subject && a.body === b.body;
}

/** Antwortentwurf (operator 27.09.2026): An, Cc, Betreff und Text frei bearbeitbar, Anhänge aus
 * dem DMS verknüpfen (Verweis, keine Kopie) oder vom lokalen Rechner hochladen, Anhänge
 * entfernen. Senden läuft weiter über Einreichen und Freigabe nach den Regeln M20-03/M20-04. */
export function DraftEditor({ message, onUpdated }: { message: Message; onUpdated: (next: Message) => void }) {
  const t = useTranslations("Mail");
  const ta = useTranslations("Mail.draftAttachments");
  const server = draftFields(message);
  const [to, setTo] = useState(server.to);
  const [cc, setCc] = useState(server.cc);
  const [subject, setSubject] = useState(server.subject);
  const [body, setBody] = useState(server.body);
  // Review 1.36.0: the same draft can come back from outside the editor with a newer text
  // ("Vorschlag übernehmen", "Vorbereiten", "Antworten" return the open draft). `seen` is the
  // last server version received through props, `pristine` the local values that count as
  // "no unsaved edits", `echo` the server answer to this editor's own save, `incoming` a newer
  // server version waiting for the user's decision because local edits would be lost.
  const [seen, setSeen] = useState(server);
  const [pristine, setPristine] = useState(server);
  const [echo, setEcho] = useState<DraftFields | null>(null);
  const [incoming, setIncoming] = useState<DraftFields | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<DraftAttachment[] | null>(null);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [showDms, setShowDms] = useState(false);
  const [dmsQuery, setDmsQuery] = useState("");
  const [dmsHits, setDmsHits] = useState<DraftAttachment[] | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  const applyFields = (next: DraftFields) => {
    setTo(next.to);
    setCc(next.cc);
    setSubject(next.subject);
    setBody(next.body);
    setPristine(next);
    setIncoming(null);
  };

  // Adjusting state while rendering when the prop changes (React: "storing information from
  // previous renders"), so the inputs never show the stale text for a committed frame.
  if (!sameFields(server, seen)) {
    setSeen(server);
    if (echo && sameFields(server, echo)) setEcho(null);
    else if (sameFields({ to, cc, subject, body }, pristine)) applyFields(server);
    else setIncoming(server);
  }

  useEffect(() => {
    setAttachments(null);
    setAttachmentError(null);
    void bff<DraftAttachment[]>(`/api/bff/mail/messages/${message.id}/attachments`).then((res) => {
      if (res.ok) setAttachments(res.data);
      else setAttachmentError(res.message);
    });
  }, [message.id]);

  const save = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<Message>(`/api/bff/mail/messages/${message.id}/draft`, {
      method: "PATCH",
      body: JSON.stringify({
        subject: subject.trim(),
        body,
        to_addresses: splitAddresses(to),
        cc_addresses: splitAddresses(cc),
      }),
    });
    setBusy(false);
    if (res.ok) {
      // The saved values are the new baseline; the parent hands the answer back as a prop.
      setPristine({ to, cc, subject, body });
      setEcho(draftFields(res.data));
      onUpdated(res.data);
    } else setError(res.status === 422 ? t("invalidAddresses") : res.message);
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

  const removeAttachment = async (documentId: string) => {
    setBusy(true);
    setAttachmentError(null);
    const res = await bff<DraftAttachment[]>(`/api/bff/mail/messages/${message.id}/attachments/${documentId}`, { method: "DELETE" });
    setBusy(false);
    if (res.ok) setAttachments(res.data);
    else setAttachmentError(res.message);
  };

  const searchDms = async () => {
    if (dmsQuery.trim().length < 2) return;
    setBusy(true);
    setAttachmentError(null);
    const res = await bff<DraftAttachment[]>(
      `/api/bff/mail/messages/${message.id}/attachment-candidates?q=${encodeURIComponent(dmsQuery.trim())}`,
    );
    setBusy(false);
    if (res.ok) setDmsHits(res.data);
    else setAttachmentError(res.message);
  };

  const addFromDms = async (documentId: string) => {
    setBusy(true);
    setAttachmentError(null);
    const res = await bff<DraftAttachment[]>(`/api/bff/mail/messages/${message.id}/attachments`, {
      method: "POST",
      body: JSON.stringify({ document_id: documentId }),
    });
    setBusy(false);
    if (res.ok) {
      setAttachments(res.data);
      setDmsHits((prev) => prev?.filter((h) => h.document_id !== documentId) ?? null);
    } else setAttachmentError(res.message);
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setAttachmentError(null);
    const form = new FormData();
    form.append("file", file, file.name);
    const res = await bff<DraftAttachment[]>(`/api/bff/mail/messages/${message.id}/attachments/upload`, {
      method: "POST",
      body: form,
    });
    setBusy(false);
    if (fileInput.current) fileInput.current.value = "";
    if (res.ok) setAttachments(res.data);
    else setAttachmentError(res.message);
  };

  const attached = new Set((attachments ?? []).map((a) => a.document_id));

  return (
    <div className="flex flex-col gap-3" data-testid="mail-draft-editor">
      {message.rejection_note ? <p className={ui.notice}>{t("rejectionNote", { note: message.rejection_note })}</p> : null}
      {incoming ? (
        <div className={`${ui.notice} flex flex-col gap-2`} role="status" data-testid="mail-draft-newer-version">
          <span>{t("draftNewerVersion.hint")}</span>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={ui.button} onClick={() => applyFields(incoming)}>
              {t("draftNewerVersion.take")}
            </button>
            <button type="button" className={ui.button} onClick={() => setIncoming(null)}>
              {t("draftNewerVersion.keep")}
            </button>
          </div>
        </div>
      ) : null}
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("to")}</span>
        <input className={ui.input} value={to} onChange={(e) => setTo(e.target.value)} disabled={busy} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("cc")}</span>
        <input className={ui.input} value={cc} onChange={(e) => setCc(e.target.value)} disabled={busy} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("subject")}</span>
        <input className={ui.input} value={subject} onChange={(e) => setSubject(e.target.value)} disabled={busy} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("body")}</span>
        <textarea className={ui.input} rows={10} value={body} onChange={(e) => setBody(e.target.value)} disabled={busy} />
      </label>

      <section className="flex flex-col gap-2 rounded-md border border-border-soft p-2" data-testid="mail-draft-attachments">
        <span className={ui.label}>{ta("title")}</span>
        {attachments === null ? (
          <p className="text-xs text-muted">{ta("loading")}</p>
        ) : attachments.length === 0 ? (
          <p className="text-xs text-muted">{ta("empty")}</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {attachments.map((a) => (
              <li key={a.document_id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <span className="min-w-0 break-words [overflow-wrap:anywhere]">
                  {a.filename} <span className="text-xs text-subtle">({formatSize(a.size)})</span>
                </span>
                <button
                  type="button"
                  className={ui.button}
                  disabled={busy}
                  onClick={() => void removeAttachment(a.document_id)}
                  aria-label={ta("removeLabel", { name: a.filename })}
                >
                  {ta("remove")}
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className={ui.button} disabled={busy} onClick={() => fileInput.current?.click()}>
            {ta("upload")}
          </button>
          <input
            ref={fileInput}
            type="file"
            className="hidden"
            aria-label={ta("uploadInput")}
            data-testid="mail-draft-upload-input"
            onChange={(e) => void upload(e.target.files?.[0])}
          />
          <button type="button" className={ui.button} disabled={busy} onClick={() => setShowDms((v) => !v)}>
            {ta("fromDms")}
          </button>
        </div>
        {showDms ? (
          <div className="flex flex-col gap-2 border-t border-border-soft pt-2">
            <div className="flex flex-wrap items-center gap-2">
              <input
                aria-label={ta("searchPlaceholder")}
                className={`${ui.input} min-w-0 flex-1`}
                placeholder={ta("searchPlaceholder")}
                value={dmsQuery}
                onChange={(e) => setDmsQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void searchDms();
                  }
                }}
                disabled={busy}
              />
              <button type="button" className={ui.button} disabled={busy || dmsQuery.trim().length < 2} onClick={() => void searchDms()}>
                {ta("search")}
              </button>
            </div>
            {dmsHits === null ? null : dmsHits.length === 0 ? (
              <p className="text-xs text-muted">{ta("noHits")}</p>
            ) : (
              <ul className="flex flex-col gap-1">
                {dmsHits.map((h) => (
                  <li key={h.document_id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span className="min-w-0 break-words [overflow-wrap:anywhere]">
                      {h.title} <span className="text-xs text-subtle">({h.filename}, {formatSize(h.size)})</span>
                    </span>
                    <button
                      type="button"
                      className={ui.button}
                      disabled={busy || attached.has(h.document_id)}
                      onClick={() => void addFromDms(h.document_id)}
                    >
                      {attached.has(h.document_id) ? ta("added") : ta("add")}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}
        {attachmentError ? (
          <p role="alert" className={ui.alert}>
            {attachmentError}
          </p>
        ) : null}
      </section>

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={ui.button} disabled={busy || incoming !== null} onClick={() => void save()}>
          {t("save")}
        </button>
        <button
          type="button"
          className={ui.primary}
          disabled={busy || incoming !== null || !to.trim() || !body.trim()}
          onClick={() => void submit()}
        >
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
