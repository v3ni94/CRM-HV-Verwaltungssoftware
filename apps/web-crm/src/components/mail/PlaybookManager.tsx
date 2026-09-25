"use client";

import { useState } from "react";

import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type Playbook = {
  id: string;
  title: string;
  category: string | null;
  keywords: string[];
  summary: string;
  steps: string[];
  reply_template: string | null;
  source_ticket_id: string | null;
  status: "draft" | "active" | "archived";
  usage_count: number;
  created_by: string | null;
};

type Form = {
  title: string;
  category: string;
  keywords: string;
  summary: string;
  steps: string;
  reply_template: string;
  status: Playbook["status"];
};

const EMPTY: Form = { title: "", category: "", keywords: "", summary: "", steps: "", reply_template: "", status: "draft" };

function toForm(p: Playbook): Form {
  return {
    title: p.title,
    category: p.category ?? "",
    keywords: p.keywords.join(", "),
    summary: p.summary,
    steps: p.steps.join("\n"),
    reply_template: p.reply_template ?? "",
    status: p.status,
  };
}

function toPayload(f: Form): Record<string, unknown> {
  return {
    title: f.title.trim(),
    category: f.category.trim() || null,
    keywords: f.keywords
      .split(",")
      .map((k) => k.trim())
      .filter(Boolean),
    summary: f.summary,
    steps: f.steps
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean),
    reply_template: f.reply_template.trim() || null,
    status: f.status,
  };
}

function PlaybookForm({
  form,
  onChange,
  onSave,
  busy,
  t,
}: {
  form: Form;
  onChange: (next: Form) => void;
  onSave: () => void;
  busy: boolean;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("titleLabel")}</span>
        <input className={ui.input} value={form.title} onChange={(e) => onChange({ ...form, title: e.target.value })} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("category")}</span>
        <input className={ui.input} value={form.category} onChange={(e) => onChange({ ...form, category: e.target.value })} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("keywords")}</span>
        <input className={ui.input} value={form.keywords} onChange={(e) => onChange({ ...form, keywords: e.target.value })} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("summary")}</span>
        <textarea className={ui.input} rows={2} value={form.summary} onChange={(e) => onChange({ ...form, summary: e.target.value })} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("steps")}</span>
        <textarea className={ui.input} rows={4} value={form.steps} onChange={(e) => onChange({ ...form, steps: e.target.value })} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("replyTemplate")}</span>
        <textarea className={ui.input} rows={4} value={form.reply_template} onChange={(e) => onChange({ ...form, reply_template: e.target.value })} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("status.draft")}</span>
        <select className={ui.input} value={form.status} onChange={(e) => onChange({ ...form, status: e.target.value as Playbook["status"] })}>
          <option value="draft">{t("status.draft")}</option>
          <option value="active">{t("status.active")}</option>
          <option value="archived">{t("status.archived")}</option>
        </select>
      </label>
      <button type="button" className={ui.primary} disabled={busy || !form.title.trim()} onClick={onSave}>
        {t("save")}
      </button>
    </div>
  );
}

export function PlaybookManager({
  playbooks,
  canWrite,
  canDelete,
}: {
  playbooks: Playbook[];
  canWrite: boolean;
  canDelete: boolean;
}) {
  const t = useTranslations("MailPlaybooks");
  const [items, setItems] = useState(playbooks);
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [busy, setBusy] = useState(false);

  const startNew = () => {
    setEditing("new");
    setForm(EMPTY);
  };
  const startEdit = (p: Playbook) => {
    setEditing(p.id);
    setForm(toForm(p));
  };

  const save = async () => {
    setBusy(true);
    if (editing === "new") {
      const res = await bff<Playbook>("/api/bff/mail/playbooks", { method: "POST", body: JSON.stringify(toPayload(form)) });
      setBusy(false);
      if (res.ok) {
        setItems([...items, res.data]);
        setEditing(null);
      }
      return;
    }
    const res = await bff<Playbook>(`/api/bff/mail/playbooks/${editing}`, { method: "PATCH", body: JSON.stringify(toPayload(form)) });
    setBusy(false);
    if (res.ok) {
      setItems(items.map((p) => (p.id === res.data.id ? res.data : p)));
      setEditing(null);
    }
  };

  const activate = async (p: Playbook) => {
    const res = await bff<Playbook>(`/api/bff/mail/playbooks/${p.id}`, { method: "PATCH", body: JSON.stringify({ status: "active" }) });
    if (res.ok) setItems(items.map((x) => (x.id === p.id ? res.data : x)));
  };

  const remove = async (p: Playbook) => {
    const res = await bff<null>(`/api/bff/mail/playbooks/${p.id}`, { method: "DELETE" });
    if (res.ok) setItems(items.filter((x) => x.id !== p.id));
  };

  return (
    <div className="flex flex-col gap-4">
      {canWrite ? (
        <div className="flex items-center justify-between">
          {editing === null ? (
            <button type="button" className={ui.button} onClick={startNew}>
              {t("new")}
            </button>
          ) : null}
        </div>
      ) : null}

      {editing !== null ? (
        <section className={`${ui.card} flex flex-col gap-2`}>
          <PlaybookForm form={form} onChange={setForm} onSave={() => void save()} busy={busy} t={t} />
          <button type="button" className={ui.button} onClick={() => setEditing(null)}>
            {t("backToMail")}
          </button>
        </section>
      ) : null}

      {items.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((p) => (
            <li key={p.id} className={`${ui.card} flex flex-col gap-1.5`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold">{p.title}</h3>
                <span className={ui.badge}>{t(`status.${p.status}`)}</span>
              </div>
              {p.category ? <p className="text-xs text-muted">{p.category}</p> : null}
              <p className="text-sm">{p.summary}</p>
              {p.keywords.length > 0 ? <p className="text-xs text-subtle">{p.keywords.join(", ")}</p> : null}
              <p className="text-xs text-muted">{t("usageCount", { count: p.usage_count })}</p>
              {canWrite ? (
                <div className="flex flex-wrap gap-2">
                  <button type="button" className={ui.button} onClick={() => startEdit(p)}>
                    {t("save")}
                  </button>
                  {p.status === "draft" ? (
                    <button type="button" className={ui.primary} onClick={() => void activate(p)}>
                      {t("activate")}
                    </button>
                  ) : null}
                  {canDelete ? (
                    <button type="button" className={ui.danger} onClick={() => void remove(p)}>
                      {t("delete")}
                    </button>
                  ) : null}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
