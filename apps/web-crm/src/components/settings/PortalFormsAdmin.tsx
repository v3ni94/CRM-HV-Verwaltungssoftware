"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type PortalFormFieldType = "text" | "number" | "date" | "select" | "file";
export type PortalFormField = {
  key: string;
  label: string;
  type: PortalFormFieldType;
  required: boolean;
  options?: string[] | null;
};
export type PortalFormTemplate = {
  id: string;
  name: string;
  description: string | null;
  category: string;
  audience: "tenant" | "owner" | "all";
  active: boolean;
  sort_order: number;
  fields: PortalFormField[];
};

const FIELD_TYPES: PortalFormFieldType[] = ["text", "number", "date", "select", "file"];
const AUDIENCES: PortalFormTemplate["audience"][] = ["all", "tenant", "owner"];

function slugify(label: string): string {
  return (
    label
      .toLowerCase()
      .replace(/ä/g, "ae")
      .replace(/ö/g, "oe")
      .replace(/ü/g, "ue")
      .replace(/ß/g, "ss")
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 60) || "feld"
  );
}

function FieldsEditor({ fields, onChange }: { fields: PortalFormField[]; onChange: (fields: PortalFormField[]) => void }) {
  const t = useTranslations("PortalForms");
  const [label, setLabel] = useState("");
  const [type, setType] = useState<PortalFormFieldType>("text");
  const [options, setOptions] = useState("");
  return (
    <div className="flex flex-col gap-1.5">
      <span className={ui.label}>{t("fields")}</span>
      <ul className="flex flex-col gap-1">
        {fields.map((f, i) => (
          <li key={f.key} className="flex flex-wrap items-center gap-2 text-sm">
            <span className="flex-1">
              {f.label} <span className="text-xs text-muted">({t(`fieldTypes.${f.type}`)}</span>
              {f.type === "select" && f.options ? <span className="text-xs text-muted">: {f.options.join(", ")}</span> : null}
              <span className="text-xs text-muted">)</span>
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
        <input className={ui.input} placeholder={t("newFieldLabel")} aria-label={t("newFieldLabel")} value={label} onChange={(e) => setLabel(e.target.value)} />
        <select className={ui.input} aria-label={t("fieldType")} value={type} onChange={(e) => setType(e.target.value as PortalFormFieldType)}>
          {FIELD_TYPES.map((ft) => (
            <option key={ft} value={ft}>
              {t(`fieldTypes.${ft}`)}
            </option>
          ))}
        </select>
        {type === "select" ? (
          <input
            className={ui.input}
            placeholder={t("optionsPlaceholder")}
            aria-label={t("options")}
            value={options}
            onChange={(e) => setOptions(e.target.value)}
          />
        ) : null}
        <button
          type="button"
          className={ui.buttonSm}
          disabled={!label.trim() || (type === "select" && !options.trim())}
          onClick={() => {
            let key = slugify(label);
            while (fields.some((f) => f.key === key)) key = `${key}_2`;
            const opts = type === "select" ? options.split(",").map((o) => o.trim()).filter(Boolean) : null;
            onChange([...fields, { key, label: label.trim(), type, required: false, options: opts }]);
            setLabel("");
            setOptions("");
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
  initial?: PortalFormTemplate;
  onSaved: (tpl: PortalFormTemplate) => void;
  onCancel?: () => void;
}) {
  const t = useTranslations("PortalForms");
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [category, setCategory] = useState(initial?.category ?? "");
  const [audience, setAudience] = useState<PortalFormTemplate["audience"]>(initial?.audience ?? "all");
  const [fields, setFields] = useState<PortalFormField[]>(initial?.fields ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!name.trim()) {
      setError(t("errors.name"));
      return;
    }
    if (!category.trim()) {
      setError(t("errors.category"));
      return;
    }
    setBusy(true);
    setError(null);
    const body = { name: name.trim(), description: description.trim() || null, category: category.trim(), audience, fields };
    const res = initial
      ? await bff<PortalFormTemplate>(`/api/bff/portal-admin/forms/${initial.id}`, { method: "PATCH", body: JSON.stringify(body) })
      : await bff<PortalFormTemplate>("/api/bff/portal-admin/forms", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) onSaved(res.data);
    else setError(res.message);
  }

  return (
    <div className={`${ui.card} flex flex-col gap-3`} data-testid="portal-form-editor">
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("name")}</span>
        <input className={ui.input} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("description2")}</span>
        <textarea className={ui.input} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("category")}</span>
        <input className={ui.input} value={category} onChange={(e) => setCategory(e.target.value)} />
      </label>
      <p className={ui.help}>{t("categoryHelp")}</p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("audience")}</span>
        <select className={ui.input} value={audience} onChange={(e) => setAudience(e.target.value as PortalFormTemplate["audience"])}>
          {AUDIENCES.map((a) => (
            <option key={a} value={a}>
              {t(`audiences.${a}`)}
            </option>
          ))}
        </select>
      </label>
      <FieldsEditor fields={fields} onChange={setFields} />
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="flex gap-2">
        <button type="button" className={ui.primary} disabled={busy} onClick={submit}>
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

/** Portalformulare (A56): Vorlagen je Mandant mit Feldern, Zielgruppe und Ticketkategorie.
 *  Eine Einreichung im Portal wird zum Ticket der Kategorie; die Pflege braucht
 *  tenant_settings:update (vom Backend geprüft). */
export function PortalFormsAdmin({ initialTemplates, canManage }: { initialTemplates: PortalFormTemplate[]; canManage: boolean }) {
  const t = useTranslations("PortalForms");
  const [templates, setTemplates] = useState(initialTemplates);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle(tpl: PortalFormTemplate) {
    const res = await bff<PortalFormTemplate>(`/api/bff/portal-admin/forms/${tpl.id}`, {
      method: "PATCH",
      body: JSON.stringify({ active: !tpl.active }),
    });
    if (res.ok) setTemplates((list) => list.map((x) => (x.id === tpl.id ? res.data : x)));
    else setError(res.message);
  }

  async function remove(tpl: PortalFormTemplate) {
    if (!window.confirm(t("confirmDelete", { name: tpl.name }))) return;
    const res = await bff<null>(`/api/bff/portal-admin/forms/${tpl.id}`, { method: "DELETE" });
    if (res.ok) setTemplates((list) => list.filter((x) => x.id !== tpl.id));
    else setError(res.message);
  }

  return (
    <div className="flex flex-col gap-4">
      <p className={ui.notice}>{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {canManage && !creating ? (
        <div>
          <button type="button" className={ui.button} onClick={() => setCreating(true)}>
            {t("newTemplate")}
          </button>
        </div>
      ) : null}
      {creating ? (
        <TemplateForm
          onSaved={(tpl) => {
            setTemplates((list) => [...list, tpl]);
            setCreating(false);
          }}
          onCancel={() => setCreating(false)}
        />
      ) : null}
      {templates.length === 0 && !creating ? <p className="text-sm text-muted">{t("empty")}</p> : null}
      <ul className="flex flex-col gap-3">
        {templates.map((tpl) =>
          editing === tpl.id ? (
            <li key={tpl.id}>
              <TemplateForm
                initial={tpl}
                onSaved={(next) => {
                  setTemplates((list) => list.map((x) => (x.id === tpl.id ? next : x)));
                  setEditing(null);
                }}
                onCancel={() => setEditing(null)}
              />
            </li>
          ) : (
            <li key={tpl.id} className={`${ui.card} flex flex-col gap-2`} data-testid="portal-form-template">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{tpl.name}</span>
                <StatusPill label={tpl.active ? t("activeState") : t("inactiveState")} variant={tpl.active ? "success" : "neutral"} />
                <span className={ui.badge}>{t(`audiences.${tpl.audience}`)}</span>
                <span className="text-xs text-muted">
                  {t("category")}: {tpl.category}
                </span>
              </div>
              {tpl.description ? <p className="text-sm text-muted">{tpl.description}</p> : null}
              <p className="text-xs text-muted">
                {tpl.fields.length === 0
                  ? t("noFields")
                  : tpl.fields.map((f) => `${f.label}${f.required ? " *" : ""}`).join(", ")}
              </p>
              {canManage ? (
                <div className="flex flex-wrap gap-2">
                  <button type="button" className={ui.buttonSm} onClick={() => setEditing(tpl.id)}>
                    {t("edit")}
                  </button>
                  <button type="button" className={ui.buttonSm} onClick={() => toggle(tpl)}>
                    {tpl.active ? t("deactivate") : t("activate")}
                  </button>
                  <button type="button" className={ui.buttonSm} onClick={() => remove(tpl)}>
                    {t("delete")}
                  </button>
                </div>
              ) : null}
            </li>
          ),
        )}
      </ul>
    </div>
  );
}
