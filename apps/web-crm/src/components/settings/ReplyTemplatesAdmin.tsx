"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type ReplyTemplate = {
  id: string;
  name: string;
  subject: string;
  body: string;
  topic: string | null;
  attachment_document_ids: string[];
  active: boolean;
};

type DocumentRef = { id: string; title: string; filename: string };
type Competence = { code: string; label: string };

type FormState = {
  name: string;
  subject: string;
  body: string;
  topic: string;
  attachments: DocumentRef[];
};

const EMPTY: FormState = { name: "", subject: "", body: "", topic: "", attachments: [] };

/** Dokumentsuche für Standardanhänge: die Suche läuft serverseitig über ?q= der Seite (GET
 *  /documents bleibt außerhalb des BFF-Proxys); die Treffer kommen als Props, der Formular-
 *  zustand bleibt bei der weichen Navigation erhalten. Übernahme als Verweis, keine Kopie. */
function AttachmentPicker({
  attachments,
  onChange,
  query,
  hits,
}: {
  attachments: DocumentRef[];
  onChange: (next: DocumentRef[]) => void;
  query: string;
  hits: DocumentRef[] | null;
}) {
  const t = useTranslations("ReplyTemplates");
  const router = useRouter();
  const [q, setQ] = useState(query);

  function search() {
    const term = q.trim();
    if (term.length < 2) return;
    router.push(`/einstellungen/antwortvorlagen?q=${encodeURIComponent(term)}`, { scroll: false });
  }

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <span className={ui.label}>{t("attachments")}</span>
      {attachments.length > 0 ? (
        <ul className="flex flex-col gap-1" data-testid="reply-template-attachments">
          {attachments.map((a) => (
            <li key={a.id} className="flex min-w-0 items-center justify-between gap-2 text-sm">
              <span className="min-w-0 truncate">{a.title || a.filename}</span>
              <button type="button" className={ui.buttonSm} onClick={() => onChange(attachments.filter((x) => x.id !== a.id))}>
                {t("remove")}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          className={ui.input}
          aria-label={t("searchDocuments")}
          placeholder={t("searchDocuments")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              search();
            }
          }}
        />
        <button type="button" className={ui.button} disabled={q.trim().length < 2} onClick={search}>
          {t("search")}
        </button>
      </div>
      {hits ? (
        hits.length === 0 ? (
          <p className="text-xs text-muted">{t("noResults")}</p>
        ) : (
          <ul className="flex flex-col gap-1" data-testid="reply-template-document-hits">
            {hits
              .filter((h) => !attachments.some((a) => a.id === h.id))
              .map((h) => (
                <li key={h.id} className="flex min-w-0 items-center justify-between gap-2 text-sm">
                  <span className="min-w-0 truncate">{h.title || h.filename}</span>
                  <button type="button" className={ui.buttonSm} onClick={() => onChange([...attachments, h])}>
                    {t("addAttachment")}
                  </button>
                </li>
              ))}
          </ul>
        )
      ) : null}
    </div>
  );
}

function TemplateForm({
  initial,
  topics,
  placeholders,
  canSearchDocuments,
  documentQuery,
  documentHits,
  onCancel,
  onSaved,
}: {
  initial: ReplyTemplate | null;
  topics: Competence[];
  placeholders: string[];
  canSearchDocuments: boolean;
  documentQuery: string;
  documentHits: DocumentRef[] | null;
  onCancel: () => void;
  onSaved: (tpl: ReplyTemplate) => void;
}) {
  const t = useTranslations("ReplyTemplates");
  const [form, setForm] = useState<FormState>(
    initial
      ? {
          name: initial.name,
          subject: initial.subject,
          body: initial.body,
          topic: initial.topic ?? "",
          attachments: initial.attachment_document_ids.map((id) => ({ id, title: "", filename: id })),
        }
      : EMPTY,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!initial || initial.attachment_document_ids.length === 0) return;
    let cancelled = false;
    void bff<ReplyTemplate & { attachments: { document_id: string; title: string | null; filename: string | null }[] }>(
      `/api/bff/tickets/reply-templates/${initial.id}`,
    ).then((res) => {
      if (cancelled || !res.ok) return;
      setForm((prev) => ({
        ...prev,
        attachments: res.data.attachments.map((a) => ({ id: a.document_id, title: a.title ?? "", filename: a.filename ?? a.document_id })),
      }));
    });
    return () => {
      cancelled = true;
    };
  }, [initial]);

  async function save() {
    setBusy(true);
    setError(null);
    const payload = {
      name: form.name.trim(),
      subject: form.subject.trim(),
      body: form.body,
      topic: form.topic || null,
      attachment_document_ids: form.attachments.map((a) => a.id),
    };
    const res = initial
      ? await bff<ReplyTemplate>(`/api/bff/tickets/reply-templates/${initial.id}`, { method: "PATCH", body: JSON.stringify(payload) })
      : await bff<ReplyTemplate>("/api/bff/tickets/reply-templates", { method: "POST", body: JSON.stringify(payload) });
    setBusy(false);
    if (res.ok) onSaved(res.data);
    else setError(res.message);
  }

  return (
    <form
      className={`${ui.card} flex min-w-0 flex-col gap-3`}
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("name")}</span>
        <input className={ui.input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required maxLength={150} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("subject")}</span>
        <input className={ui.input} value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} required maxLength={300} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("body")}</span>
        <textarea className={ui.input} rows={8} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} required />
      </label>
      <p className="text-xs text-muted">
        {t("placeholders")}: {placeholders.map((p) => `{${p}}`).join(", ")}. {t("placeholdersHint")}
      </p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("topic")}</span>
        {topics.length > 0 ? (
          <select className={ui.input} value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })}>
            <option value="">{t("noTopic")}</option>
            {topics.map((c) => (
              <option key={c.code} value={c.code}>
                {c.label}
              </option>
            ))}
          </select>
        ) : (
          <input className={ui.input} value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} maxLength={32} />
        )}
      </label>
      {canSearchDocuments ? (
        <AttachmentPicker
          attachments={form.attachments}
          onChange={(next) => setForm({ ...form, attachments: next })}
          query={documentQuery}
          hits={documentHits}
        />
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className={ui.formActions}>
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("save")}
        </button>
        <button type="button" className={ui.button} onClick={onCancel}>
          {t("cancel")}
        </button>
      </div>
    </form>
  );
}

export function ReplyTemplatesAdmin({
  initialTemplates,
  canManage,
  canPickTopic,
  canSearchDocuments,
  documentQuery = "",
  documentHits = null,
}: {
  initialTemplates: ReplyTemplate[];
  canManage: boolean;
  canPickTopic: boolean;
  canSearchDocuments: boolean;
  documentQuery?: string;
  documentHits?: DocumentRef[] | null;
}) {
  const t = useTranslations("ReplyTemplates");
  const [templates, setTemplates] = useState(initialTemplates);
  const [editing, setEditing] = useState<ReplyTemplate | null | "new">(null);
  const [topics, setTopics] = useState<Competence[]>([]);
  const [placeholders, setPlaceholders] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void bff<string[]>("/api/bff/tickets/reply-templates/placeholders").then((res) => {
      if (!cancelled && res.ok) setPlaceholders(res.data);
    });
    if (canPickTopic) {
      void bff<Competence[]>("/api/bff/tenant/competence-catalogue").then((res) => {
        if (!cancelled && res.ok) setTopics(res.data);
      });
    }
    return () => {
      cancelled = true;
    };
  }, [canPickTopic]);

  const topicLabel = (code: string | null) => (code ? (topics.find((c) => c.code === code)?.label ?? code) : t("noTopic"));

  async function toggleActive(tpl: ReplyTemplate) {
    setError(null);
    const res = await bff<ReplyTemplate>(`/api/bff/tickets/reply-templates/${tpl.id}`, {
      method: "PATCH",
      body: JSON.stringify({ active: !tpl.active }),
    });
    if (res.ok) setTemplates((prev) => prev.map((x) => (x.id === tpl.id ? res.data : x)));
    else setError(res.message);
  }

  async function remove(tpl: ReplyTemplate) {
    if (!window.confirm(t("deleteConfirm"))) return;
    setError(null);
    const res = await bff<unknown>(`/api/bff/tickets/reply-templates/${tpl.id}`, { method: "DELETE" });
    if (res.ok) setTemplates((prev) => prev.filter((x) => x.id !== tpl.id));
    else setError(res.message);
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      {canManage ? (
        editing === null ? (
          <button type="button" className={`${ui.primary} w-fit`} onClick={() => setEditing("new")}>
            {t("newTemplate")}
          </button>
        ) : (
          <TemplateForm
            initial={editing === "new" ? null : editing}
            topics={topics}
            placeholders={placeholders}
            canSearchDocuments={canSearchDocuments}
            documentQuery={documentQuery}
            documentHits={documentHits}
            onCancel={() => setEditing(null)}
            onSaved={(tpl) => {
              setTemplates((prev) => (prev.some((x) => x.id === tpl.id) ? prev.map((x) => (x.id === tpl.id ? tpl : x)) : [...prev, tpl]));
              setEditing(null);
            }}
          />
        )
      ) : (
        <p className="text-xs text-muted">{t("readOnlyHint")}</p>
      )}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {templates.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2" data-testid="reply-templates">
          {templates.map((tpl) => (
            <li key={tpl.id} className={`${ui.card} flex min-w-0 flex-col gap-2`}>
              <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                <span className="min-w-0 break-words font-medium">{tpl.name}</span>
                <span className="flex flex-wrap items-center gap-2">
                  <StatusPill variant="neutral" label={topicLabel(tpl.topic)} />
                  <StatusPill variant={tpl.active ? "success" : "neutral"} label={tpl.active ? t("activeState") : t("inactiveState")} />
                </span>
              </div>
              <p className="min-w-0 break-words text-sm text-muted">{tpl.subject}</p>
              <p className="min-w-0 whitespace-pre-wrap break-words text-sm [overflow-wrap:anywhere]">{tpl.body}</p>
              {tpl.attachment_document_ids.length > 0 ? (
                <p className="text-xs text-muted">{t("attachmentCount", { count: tpl.attachment_document_ids.length })}</p>
              ) : null}
              {canManage ? (
                <div className="flex flex-wrap gap-2">
                  <button type="button" className={ui.buttonSm} onClick={() => setEditing(tpl)}>
                    {t("edit")}
                  </button>
                  <button type="button" className={ui.buttonSm} onClick={() => void toggleActive(tpl)}>
                    {tpl.active ? t("deactivate") : t("activate")}
                  </button>
                  <button type="button" className={ui.buttonSm} onClick={() => void remove(tpl)}>
                    {t("delete")}
                  </button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
