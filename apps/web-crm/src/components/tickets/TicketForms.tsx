"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export const STATUSES = ["new", "in_progress", "waiting", "done", "closed", "rejected"] as const;
export const PRIORITIES = ["low", "normal", "high", "urgent", "immediate"] as const;

type TemplateSummary = {
  id: string;
  category: string;
  title: string;
  checklist: { key: string; label: string; required: boolean }[];
  extra_fields: { key: string; label: string; required: boolean }[];
  active: boolean;
};

export function TicketCreate() {
  const t = useTranslations("Tickets");
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("normal");
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void bff<TemplateSummary[]>("/api/bff/tickets/templates?active=true").then((res) => {
      if (res.ok) setTemplates(res.data.filter((tpl) => tpl.active));
    });
  }, []);

  const selected = templates.find((tpl) => tpl.id === templateId);

  const create = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ id: string }>("/api/bff/tickets", {
      method: "POST",
      body: JSON.stringify({
        title: title.trim() || undefined,
        public_description: description.trim() || null,
        priority,
        template_id: templateId || null,
      }),
    });
    setBusy(false);
    if (res.ok) router.push(`/tickets/${res.data.id}`);
    else setError(res.message);
  };
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("template")}</span>
          <select className={ui.input} value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
            <option value="">{t("noTemplate")}</option>
            {templates.map((tpl) => (
              <option key={tpl.id} value={tpl.id}>
                {tpl.title}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("titleField")}</span>
          <input className={ui.input} value={title} onChange={(e) => setTitle(e.target.value)} placeholder={selected?.title ?? ""} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("description")}</span>
          <input className={ui.input} value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("priority")}</span>
          <select className={ui.input} value={priority} onChange={(e) => setPriority(e.target.value)}>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {t(`priorities.${p}`)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className={`${ui.primary} ${ui.actionFull}`}
          onClick={create}
          disabled={busy || (title.trim().length < 3 && !selected)}
        >
          {t("create")}
        </button>
      </div>
      {selected && (selected.checklist.some((c) => c.required) || selected.extra_fields.some((f) => f.required)) ? (
        <p className="text-xs text-muted">
          {selected.checklist
            .filter((c) => c.required)
            .map((c) => c.label)
            .concat(selected.extra_fields.filter((f) => f.required).map((f) => f.label))
            .join(", ")}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function TicketEdit({ id, status, priority }: { id: string; status: string; priority: string }) {
  const t = useTranslations("Tickets");
  const router = useRouter();
  const [comment, setComment] = useState("");
  const [internal, setInternal] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const send = async (path: string, method: string, body: unknown) => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/tickets/${id}${path}`, { method, body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
    return res.ok;
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("status")}</span>
          <select className={ui.input} value={status} disabled={busy} onChange={(e) => send("", "PATCH", { status: e.target.value })}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`statuses.${s}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("priority")}</span>
          <select className={ui.input} value={priority} disabled={busy} onChange={(e) => send("", "PATCH", { priority: e.target.value })}>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {t(`priorities.${p}`)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="flex flex-col gap-1">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("comment")}</span>
          <textarea className={ui.input} rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} />
          {t("internal")}
        </label>
        <button
          type="button"
          className={ui.button}
          disabled={busy || !comment.trim()}
          onClick={async () => {
            if (await send("/comments", "POST", { body: comment.trim(), internal })) setComment("");
          }}
        >
          {t("addComment")}
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
