"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { PROCESS_CODES, TicketProcessBadge } from "@/components/tickets/TicketProcessBadge";
import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type ChecklistItem = { key: string; label: string; required: boolean };
export type ExtraField = {
  key: string;
  label: string;
  type: "text" | "iban" | "date" | "number" | "select";
  required: boolean;
  options?: string[] | null;
};
export type TicketTemplate = {
  id: string;
  category: string;
  title: string;
  description: string | null;
  checklist: ChecklistItem[];
  extra_fields: ExtraField[];
  default_priority: string;
  sla_hours: number | null;
  active: boolean;
  // Prozessflow (Regel M19-11): Vorgangsart, Rolle, Verknüpfungen, Fristtypen, Unterlagen.
  process_code?: string | null;
  process_label?: string | null;
  responsible_role?: string | null;
  required_links?: string[];
  deadline_type_codes?: string[];
  document_kinds?: string[];
};

const LINK_KINDS = ["contact", "unit", "property", "contract"] as const;
const DEADLINE_KINDS = [
  "contract_end",
  "contract_termination",
  "meter_calibration",
  "bank_consent",
  "document_retention_end",
  "service_contract_notice",
  "meeting_resolution_deadline",
  "energy_certificate",
  "move_in",
  "move_out",
  "maintenance",
  "note_follow_up",
  "meeting",
  "ticket_due",
] as const;
const ROLE_CODES = [
  "tenant_admin",
  "administrator",
  "standard",
  "clerk_no_delete",
  "clerk_no_accounting",
  "accountant_no_banking",
  "accountant_banking",
  "caretaker",
  "technical_clerk",
  "support",
] as const;

const PRIORITIES = ["low", "normal", "high", "urgent", "immediate"] as const;
const FIELD_TYPES = ["text", "iban", "date", "number", "select"] as const;

function slugify(label: string): string {
  return (
    label
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "") || "feld"
  );
}

function ChecklistEditor({ items, onChange }: { items: ChecklistItem[]; onChange: (items: ChecklistItem[]) => void }) {
  const t = useTranslations("TicketTemplates");
  const [label, setLabel] = useState("");
  return (
    <div className="flex flex-col gap-1.5">
      <span className={ui.label}>{t("checklist")}</span>
      <ul className="flex flex-col gap-1">
        {items.map((it, i) => (
          <li key={it.key} className="flex items-center gap-2 text-sm">
            <span className="flex-1">{it.label}</span>
            <label className="flex items-center gap-1 text-xs text-muted">
              <input
                type="checkbox"
                checked={it.required}
                onChange={(e) => {
                  const next = [...items];
                  next[i] = { ...it, required: e.target.checked };
                  onChange(next);
                }}
              />
              {t("required")}
            </label>
            <button type="button" className={ui.buttonSm} onClick={() => onChange(items.filter((x) => x.key !== it.key))}>
              {t("remove")}
            </button>
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <input className={ui.input} placeholder={t("newChecklistItem")} value={label} onChange={(e) => setLabel(e.target.value)} />
        <button
          type="button"
          className={ui.buttonSm}
          disabled={!label.trim()}
          onClick={() => {
            const key = slugify(label);
            onChange([...items, { key, label: label.trim(), required: false }]);
            setLabel("");
          }}
        >
          {t("add")}
        </button>
      </div>
    </div>
  );
}

function ExtraFieldsEditor({ fields, onChange }: { fields: ExtraField[]; onChange: (fields: ExtraField[]) => void }) {
  const t = useTranslations("TicketTemplates");
  const [label, setLabel] = useState("");
  const [type, setType] = useState<ExtraField["type"]>("text");
  return (
    <div className="flex flex-col gap-1.5">
      <span className={ui.label}>{t("extraFields")}</span>
      <ul className="flex flex-col gap-1">
        {fields.map((f, i) => (
          <li key={f.key} className="flex items-center gap-2 text-sm">
            <span className="flex-1">
              {f.label} <span className="text-xs text-muted">({t(`fieldTypes.${f.type}`)})</span>
            </span>
            <label className="flex items-center gap-1 text-xs text-muted">
              <input
                type="checkbox"
                checked={f.required}
                onChange={(e) => {
                  const next = [...fields];
                  next[i] = { ...f, required: e.target.checked };
                  onChange(next);
                }}
              />
              {t("required")}
            </label>
            <button type="button" className={ui.buttonSm} onClick={() => onChange(fields.filter((x) => x.key !== f.key))}>
              {t("remove")}
            </button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <input className={ui.input} placeholder={t("newFieldLabel")} value={label} onChange={(e) => setLabel(e.target.value)} />
        <select className={ui.input} value={type} onChange={(e) => setType(e.target.value as ExtraField["type"])}>
          {FIELD_TYPES.map((ft) => (
            <option key={ft} value={ft}>
              {t(`fieldTypes.${ft}`)}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={ui.buttonSm}
          disabled={!label.trim()}
          onClick={() => {
            const key = slugify(label);
            onChange([...fields, { key, label: label.trim(), type, required: false }]);
            setLabel("");
          }}
        >
          {t("add")}
        </button>
      </div>
    </div>
  );
}

function TemplateForm({
  initial,
  onSaved,
  onCancel,
}: {
  initial?: TicketTemplate;
  onSaved: (tpl: TicketTemplate) => void;
  onCancel?: () => void;
}) {
  const t = useTranslations("TicketTemplates");
  const [category, setCategory] = useState(initial?.category ?? "");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [priority, setPriority] = useState(initial?.default_priority ?? "normal");
  const [checklist, setChecklist] = useState<ChecklistItem[]>(initial?.checklist ?? []);
  const [extraFields, setExtraFields] = useState<ExtraField[]>(initial?.extra_fields ?? []);
  const [processCode, setProcessCode] = useState(initial?.process_code ?? "");
  const [role, setRole] = useState(initial?.responsible_role ?? "");
  const [links, setLinks] = useState<string[]>(initial?.required_links ?? []);
  const [deadlines, setDeadlines] = useState<string[]>(initial?.deadline_type_codes ?? []);
  const [documents, setDocuments] = useState<string[]>(initial?.document_kinds ?? []);
  const [newDocument, setNewDocument] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tp = useTranslations("Tickets.process");
  const tk = useTranslations("Deadlines.kind");

  function toggleIn(list: string[], value: string): string[] {
    return list.includes(value) ? list.filter((x) => x !== value) : [...list, value];
  }

  async function submit() {
    setBusy(true);
    setError(null);
    const body = {
      category: category.trim(),
      title: title.trim(),
      description: description.trim() || null,
      checklist,
      extra_fields: extraFields,
      default_priority: priority,
      process_code: processCode || null,
      responsible_role: role || null,
      required_links: links,
      deadline_type_codes: deadlines,
      document_kinds: documents,
    };
    const res = initial
      ? await bff<TicketTemplate>(`/api/bff/tickets/templates/${initial.id}`, { method: "PATCH", body: JSON.stringify(body) })
      : await bff<TicketTemplate>("/api/bff/tickets/templates", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) onSaved(res.data);
    else setError(res.message);
  }

  return (
    <div className={`${ui.card} flex flex-col gap-3`}>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("category")}</span>
        <input className={ui.input} value={category} onChange={(e) => setCategory(e.target.value)} disabled={Boolean(initial)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("titleField")}</span>
        <input className={ui.input} value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("description2")}</span>
        <textarea className={ui.input} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("defaultPriority")}</span>
        <select className={ui.input} value={priority} onChange={(e) => setPriority(e.target.value)}>
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {t(`priorities.${p}`)}
            </option>
          ))}
        </select>
      </label>
      <ChecklistEditor items={checklist} onChange={setChecklist} />
      <ExtraFieldsEditor fields={extraFields} onChange={setExtraFields} />
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("processCode")}</span>
        <select className={ui.input} value={processCode} onChange={(e) => setProcessCode(e.target.value)} data-testid="template-process">
          <option value="">{t("processNone")}</option>
          {PROCESS_CODES.map((code) => (
            <option key={code} value={code}>
              {tp(`codes.${code}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("responsibleRole")}</span>
        <select className={ui.input} value={role} onChange={(e) => setRole(e.target.value)} data-testid="template-role">
          <option value="">{t("roleNone")}</option>
          {ROLE_CODES.map((code) => (
            <option key={code} value={code}>
              {tp(`roles.${code}`)}
            </option>
          ))}
        </select>
      </label>
      <fieldset className="flex flex-col gap-1">
        <legend className={ui.label}>{t("requiredLinks")}</legend>
        <div className="flex flex-wrap gap-3 text-sm">
          {LINK_KINDS.map((kind) => (
            <label key={kind} className="flex items-center gap-1">
              <input type="checkbox" checked={links.includes(kind)} onChange={() => setLinks(toggleIn(links, kind))} />
              {tp(`links.${kind}`)}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="flex flex-col gap-1">
        <legend className={ui.label}>{t("deadlineTypes")}</legend>
        <div className="flex flex-wrap gap-3 text-sm">
          {DEADLINE_KINDS.map((kind) => (
            <label key={kind} className="flex items-center gap-1">
              <input type="checkbox" checked={deadlines.includes(kind)} onChange={() => setDeadlines(toggleIn(deadlines, kind))} />
              {tk(kind)}
            </label>
          ))}
        </div>
        <span className="text-xs text-muted">{t("deadlineTypesHint")}</span>
      </fieldset>
      <div className="flex flex-col gap-1.5">
        <span className={ui.label}>{t("documentKinds")}</span>
        <ul className="flex flex-col gap-1">
          {documents.map((doc) => (
            <li key={doc} className="flex items-center gap-2 text-sm">
              <span className="flex-1">{doc}</span>
              <button type="button" className={ui.buttonSm} onClick={() => setDocuments(documents.filter((x) => x !== doc))}>
                {t("remove")}
              </button>
            </li>
          ))}
        </ul>
        <div className="flex gap-2">
          <input className={ui.input} placeholder={t("newDocumentKind")} value={newDocument} onChange={(e) => setNewDocument(e.target.value)} />
          <button
            type="button"
            className={ui.buttonSm}
            disabled={!newDocument.trim() || documents.includes(newDocument.trim())}
            onClick={() => {
              setDocuments([...documents, newDocument.trim()]);
              setNewDocument("");
            }}
          >
            {t("add")}
          </button>
        </div>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="flex gap-2">
        <button type="button" className={ui.primary} disabled={busy || !category.trim() || !title.trim()} onClick={() => void submit()}>
          {t("save")}
        </button>
        {onCancel ? (
          <button type="button" className={ui.button} onClick={onCancel}>
            {t("cancel")}
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function TicketTemplatesAdmin({ initialTemplates, canManage }: { initialTemplates: TicketTemplate[]; canManage: boolean }) {
  const t = useTranslations("TicketTemplates");
  const [templates, setTemplates] = useState(initialTemplates);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [seedMessage, setSeedMessage] = useState<string | null>(null);
  const [seedError, setSeedError] = useState<string | null>(null);

  // Prozesskatalog (Regel M19-11): einspielen ist idempotent, danach Liste neu laden.
  async function seedCatalogue() {
    setBusyId("seed");
    setSeedError(null);
    const res = await bff<{ created: number; updated: number; kept: number }>("/api/bff/tickets/process-catalogue/seed", {
      method: "POST",
    });
    if (res.ok) {
      setSeedMessage(t("seedResult", res.data));
      const list = await bff<TicketTemplate[]>("/api/bff/tickets/templates");
      if (list.ok) setTemplates(list.data);
    } else setSeedError(res.message);
    setBusyId(null);
  }

  function upsert(tpl: TicketTemplate) {
    setTemplates((prev) => {
      const idx = prev.findIndex((p) => p.id === tpl.id);
      if (idx === -1) return [...prev, tpl];
      const next = [...prev];
      next[idx] = tpl;
      return next;
    });
    setEditingId(null);
    setCreating(false);
  }

  async function toggleActive(tpl: TicketTemplate) {
    setBusyId(tpl.id);
    const res = await bff<TicketTemplate>(`/api/bff/tickets/templates/${tpl.id}`, {
      method: "PATCH",
      body: JSON.stringify({ active: !tpl.active }),
    });
    setBusyId(null);
    if (res.ok) upsert(res.data);
  }

  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-2">
        {templates.map((tpl) =>
          editingId === tpl.id ? (
            <TemplateForm key={tpl.id} initial={tpl} onSaved={upsert} onCancel={() => setEditingId(null)} />
          ) : (
            <li key={tpl.id} className={ui.card}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex flex-col gap-1">
                  <span className="font-medium">{tpl.title}</span>
                  <span className="text-xs text-muted">{tpl.category}</span>
                  {tpl.process_code ? <TicketProcessBadge code={tpl.process_code} /> : null}
                  {tpl.description ? <span className="text-sm text-muted">{tpl.description}</span> : null}
                  <span className="text-xs text-muted">
                    {t("checklist")}: {tpl.checklist.length} · {t("extraFields")}: {tpl.extra_fields.length}
                  </span>
                </div>
                <StatusPill variant={tpl.active ? "success" : "neutral"} label={t(tpl.active ? "activeState" : "inactiveState")} />
              </div>
              {canManage ? (
                <div className="mt-2 flex gap-2">
                  <button type="button" className={ui.buttonSm} onClick={() => setEditingId(tpl.id)}>
                    {t("edit")}
                  </button>
                  <button type="button" className={ui.buttonSm} disabled={busyId === tpl.id} onClick={() => void toggleActive(tpl)}>
                    {tpl.active ? t("deactivate") : t("activate")}
                  </button>
                </div>
              ) : null}
            </li>
          ),
        )}
      </ul>
      {canManage ? (
        creating ? (
          <TemplateForm onSaved={upsert} onCancel={() => setCreating(false)} />
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={ui.primary} onClick={() => setCreating(true)}>
              {t("newTemplate")}
            </button>
            <button type="button" className={ui.button} disabled={busyId === "seed"} onClick={() => void seedCatalogue()} title={t("seedHint")}>
              {t("seedCatalogue")}
            </button>
            {seedMessage ? <span className="text-xs text-muted">{seedMessage}</span> : null}
            {seedError ? (
              <span role="alert" className={ui.alert}>
                {seedError}
              </span>
            ) : null}
          </div>
        )
      ) : null}
    </div>
  );
}
