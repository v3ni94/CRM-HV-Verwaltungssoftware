"use client";
/** Zusatzfelder des Objekts (C2, Stammdaten in der Oberfläche, 4.11 und Anhang B.28):
 *  zeigt die für Objekte definierten Felder mit ihren Werten, speichert Werte über
 *  PATCH /properties/{id} mit If-Match (Version) und legt, mit `tenant_settings:update`,
 *  ein neues Feld (Schlüssel, Bezeichnung, Typ, Auswahlwerte) über POST /custom-fields an.
 *  Werte werden je Typ als JSON gesendet (Ganzzahl als Zahl, Ja/Nein als bool, Datum als
 *  ISO-Text); ein Feld ohne Wert wird als null übertragen. */
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDecimal, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type CustomFieldDefinition = {
  id: string;
  entity_type: string;
  key: string;
  label: string;
  field_type: string;
  required: boolean;
  group: string | null;
  valid_for_management_types: string[];
  options: string[];
  description: string | null;
  sort_order: number;
};

/** Feldtypen, die die Objektseite selbst erfassen kann; Verknüpfungstypen bleiben der
 *  Schnittstelle vorbehalten und werden nur angezeigt. */
const EDITABLE_TYPES = ["string", "text", "integer", "number", "amount", "bool", "date", "choice", "url"] as const;
const KEY_PATTERN = /^[a-z][a-z0-9_]{0,62}$/;

function display(definition: CustomFieldDefinition, value: unknown, yes: string, no: string): string {
  if (value == null || value === "") return "";
  switch (definition.field_type) {
    case "bool":
      return value ? yes : no;
    case "date":
      return formatDate(String(value));
    case "amount":
      return formatEur(String(value));
    case "number":
      return formatDecimal(String(value), 2);
    default:
      return String(value);
  }
}

function toDraft(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

function toValue(definition: CustomFieldDefinition, draft: string): unknown {
  const text = draft.trim();
  if (text === "") return null;
  switch (definition.field_type) {
    case "integer":
      return Number.parseInt(text, 10);
    case "number":
    case "amount":
      return text.replace(",", ".");
    case "bool":
      return text === "true";
    default:
      return text;
  }
}

export function CustomFieldsPanel({
  propertyId,
  version,
  values,
  managementType,
  canEdit,
  canDefine,
}: {
  propertyId: string;
  version: number;
  values: Record<string, unknown>;
  managementType: string;
  canEdit: boolean;
  canDefine: boolean;
}) {
  const t = useTranslations("Properties.customFields");
  const router = useRouter();
  const [definitions, setDefinitions] = useState<CustomFieldDefinition[] | null>(null);
  const [editing, setEditing] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [defining, setDefining] = useState(false);
  const [newField, setNewField] = useState({ key: "", label: "", field_type: "string", options: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    void bff<CustomFieldDefinition[]>("/api/bff/custom-fields?entity_type=property").then((res) => {
      if (!active) return;
      const rows = res.ok ? res.data : [];
      setDefinitions(rows.filter((d) => !d.valid_for_management_types.length || d.valid_for_management_types.includes(managementType)));
    });
    return () => {
      active = false;
    };
  }, [managementType, reload]);

  const startEdit = () => {
    const next: Record<string, string> = {};
    for (const d of definitions ?? []) next[d.key] = toDraft(values[d.key]);
    setDrafts(next);
    setError(null);
    setEditing(true);
  };

  const save = async () => {
    const payload: Record<string, unknown> = { ...values };
    for (const d of definitions ?? []) {
      if (!(EDITABLE_TYPES as readonly string[]).includes(d.field_type)) continue;
      payload[d.key] = toValue(d, drafts[d.key] ?? "");
    }
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/properties/${propertyId}`, {
      method: "PATCH",
      headers: { "If-Match": `"${version}"` },
      body: JSON.stringify({ custom_fields: payload }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.status === 412 ? t("conflict") : res.message);
      return;
    }
    setEditing(false);
    router.refresh();
  };

  const define = async () => {
    const body: Record<string, unknown> = {
      entity_type: "property",
      key: newField.key.trim(),
      label: newField.label.trim(),
      field_type: newField.field_type,
    };
    if (newField.field_type === "choice") {
      body.options = newField.options
        .split(/[\n,;]/)
        .map((o) => o.trim())
        .filter(Boolean);
    }
    setBusy(true);
    setError(null);
    const res = await bff("/api/bff/custom-fields", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setDefining(false);
    setNewField({ key: "", label: "", field_type: "string", options: "" });
    setReload((n) => n + 1);
  };

  const newFieldValid =
    KEY_PATTERN.test(newField.key.trim()) &&
    newField.label.trim().length > 0 &&
    (newField.field_type !== "choice" || newField.options.split(/[\n,;]/).some((o) => o.trim()));

  const inputId = (d: CustomFieldDefinition) => `custom-field-${d.key}`;
  const input = (d: CustomFieldDefinition) => {
    const value = drafts[d.key] ?? "";
    const set = (v: string) => setDrafts({ ...drafts, [d.key]: v });
    const id = inputId(d);
    switch (d.field_type) {
      case "bool":
        return (
          <select id={id} className={ui.input} value={value} onChange={(e) => set(e.target.value)}>
            <option value="">{t("noValue")}</option>
            <option value="true">{t("yes")}</option>
            <option value="false">{t("no")}</option>
          </select>
        );
      case "choice":
        return (
          <select id={id} className={ui.input} value={value} onChange={(e) => set(e.target.value)}>
            <option value="">{t("noValue")}</option>
            {d.options.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        );
      case "date":
        return <input id={id} type="date" className={ui.input} value={value} onChange={(e) => set(e.target.value)} />;
      case "text":
        return <textarea id={id} className={ui.input} rows={3} value={value} onChange={(e) => set(e.target.value)} />;
      case "integer":
        return <input id={id} className={ui.input} inputMode="numeric" value={value} onChange={(e) => set(e.target.value)} />;
      case "number":
      case "amount":
        return <input id={id} className={ui.input} inputMode="decimal" value={value} onChange={(e) => set(e.target.value)} />;
      case "string":
      case "url":
        return <input id={id} className={ui.input} value={value} onChange={(e) => set(e.target.value)} />;
      default:
        return <span className="text-sm text-muted">{t("apiOnly")}</span>;
    }
  };

  return (
    <section id="zusatzfelder" className={ui.card} data-testid="property-custom-fields" aria-label={t("title")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={ui.subtitle}>{t("title")}</h2>
        <div className="flex gap-1">
          {canEdit && !editing && (definitions?.length ?? 0) > 0 ? (
            <button type="button" className={ui.buttonSm} onClick={startEdit}>
              {t("edit")}
            </button>
          ) : null}
          {canDefine && !defining ? (
            <button type="button" className={ui.buttonSm} onClick={() => setDefining(true)}>
              {t("define")}
            </button>
          ) : null}
        </div>
      </div>
      {definitions === null ? (
        <p className="mt-2 text-sm text-muted">{t("loading")}</p>
      ) : definitions.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{t("empty")}</p>
      ) : (
        <dl className="mt-2 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          {definitions.map((d) => (
            <div key={d.id} className="flex flex-col gap-1">
              <dt className={ui.label}>
                {editing && (EDITABLE_TYPES as readonly string[]).includes(d.field_type) ? (
                  <label htmlFor={inputId(d)}>
                    {d.label}
                    {d.required ? " *" : ""}
                  </label>
                ) : (
                  <>
                    {d.label}
                    {d.required ? " *" : ""}
                  </>
                )}
              </dt>
              <dd>{editing ? input(d) : display(d, values[d.key], t("yes"), t("no")) || <span className="text-muted">{t("noValue")}</span>}</dd>
              {d.description ? <span className={ui.help}>{d.description}</span> : null}
            </div>
          ))}
        </dl>
      )}
      {editing ? (
        <div className={`${ui.formActions} mt-3`}>
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void save()}>
            {t("save")}
          </button>
          <button type="button" className={ui.button} onClick={() => setEditing(false)}>
            {t("cancel")}
          </button>
        </div>
      ) : null}
      {defining ? (
        <div role="dialog" aria-modal="false" aria-label={t("define")} className="mt-3 flex flex-col gap-3 border-t border-border pt-3" data-testid="custom-field-define">
          <p className={ui.help}>{t("defineHelp")}</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className={ui.label}>
              {t("label")}
              <input className={ui.input} value={newField.label} onChange={(e) => setNewField({ ...newField, label: e.target.value })} maxLength={200} required />
            </label>
            <div>
              <label className={ui.label}>
                {t("key")}
                <input className={ui.input} value={newField.key} onChange={(e) => setNewField({ ...newField, key: e.target.value })} maxLength={63} required />
              </label>
              <span className={ui.help}>{t("keyHelp")}</span>
            </div>
            <label className={ui.label}>
              {t("type")}
              <select className={ui.input} value={newField.field_type} onChange={(e) => setNewField({ ...newField, field_type: e.target.value })}>
                {EDITABLE_TYPES.map((ft) => (
                  <option key={ft} value={ft}>
                    {t(`types.${ft}`)}
                  </option>
                ))}
              </select>
            </label>
            {newField.field_type === "choice" ? (
              <label className={`${ui.label} sm:col-span-3`}>
                {t("options")}
                <input className={ui.input} value={newField.options} onChange={(e) => setNewField({ ...newField, options: e.target.value })} placeholder={t("optionsPlaceholder")} />
              </label>
            ) : null}
          </div>
          <div className={ui.formActions}>
            <button type="button" className={ui.primary} disabled={busy || !newFieldValid} onClick={() => void define()}>
              {t("create")}
            </button>
            <button type="button" className={ui.button} onClick={() => setDefining(false)}>
              {t("cancel")}
            </button>
          </div>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
