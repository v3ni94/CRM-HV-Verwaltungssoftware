"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Benutzerdefinierte Felder (P1 AP4, 4.11): Liste je Entität, Anlegen, Ändern, Löschen.
 *  Entität, interner Name und Feldtyp sind nach dem Anlegen unveränderlich, weil
 *  gespeicherte Werte davon abhängen. Feldtypen nach Anhang B.28 (Katalog
 *  `custom_field_type`). Schreibrecht `tenant_settings:update`. Endpunkte
 *  `GET|POST /custom-fields`, `PATCH|DELETE /custom-fields/{id}`. */
export type CustomField = {
  id: string;
  entity_type: string;
  key: string;
  label: string;
  field_type: string;
  required: boolean;
  group: string | null;
  valid_for_management_types: string[];
  valid_for_contract_kinds: string[];
  uniqueness: string;
  visible_in_main: boolean;
  min_value: string | null;
  max_value: string | null;
  default_value: unknown;
  options: string[];
  description: string | null;
  sort_order: number;
};
export type FieldTypeOption = { code: string; label: string };

export const ENTITY_TYPES = [
  "property",
  "building",
  "unit",
  "contract",
  "contact",
  "service_provider",
  "service_provider_relation",
] as const;
export const MANAGEMENT_TYPES = ["rental", "hoa", "hoa_with_sev"] as const;
export const UNIQUENESS = ["none", "contract", "all_contracts"] as const;
const KEY_PATTERN = /^[a-z][a-z0-9_]{0,62}$/;

type Draft = {
  entity_type: string;
  key: string;
  label: string;
  field_type: string;
  required: boolean;
  group: string;
  valid_for_management_types: string[];
  valid_for_contract_kinds: string;
  uniqueness: string;
  visible_in_main: boolean;
  min_value: string;
  max_value: string;
  default_value: string;
  options: string;
  description: string;
  sort_order: string;
};

const EMPTY: Draft = {
  entity_type: "property",
  key: "",
  label: "",
  field_type: "string",
  required: false,
  group: "",
  valid_for_management_types: [],
  valid_for_contract_kinds: "",
  uniqueness: "none",
  visible_in_main: false,
  min_value: "",
  max_value: "",
  default_value: "",
  options: "",
  description: "",
  sort_order: "0",
};

function toDraft(f: CustomField): Draft {
  return {
    entity_type: f.entity_type,
    key: f.key,
    label: f.label,
    field_type: f.field_type,
    required: f.required,
    group: f.group ?? "",
    valid_for_management_types: f.valid_for_management_types,
    valid_for_contract_kinds: f.valid_for_contract_kinds.join(", "),
    uniqueness: f.uniqueness,
    visible_in_main: f.visible_in_main,
    min_value: f.min_value ?? "",
    max_value: f.max_value ?? "",
    default_value:
      f.default_value === null || f.default_value === undefined
        ? ""
        : String(f.default_value),
    options: f.options.join(", "),
    description: f.description ?? "",
    sort_order: String(f.sort_order),
  };
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

function defaultValueOf(draft: Draft): unknown {
  const raw = draft.default_value.trim();
  if (raw === "") return null;
  if (draft.field_type === "bool") return raw === "true" || raw === "ja";
  if (draft.field_type === "integer") return Number.parseInt(raw, 10);
  if (draft.field_type === "number" || draft.field_type === "amount")
    return Number(raw);
  return raw;
}

function body(draft: Draft) {
  return {
    label: draft.label.trim(),
    required: draft.required,
    group: draft.group.trim() || null,
    valid_for_management_types: draft.valid_for_management_types,
    valid_for_contract_kinds: splitList(draft.valid_for_contract_kinds),
    uniqueness: draft.uniqueness,
    visible_in_main: draft.visible_in_main,
    min_value: draft.min_value.trim() || null,
    max_value: draft.max_value.trim() || null,
    default_value: defaultValueOf(draft),
    options: splitList(draft.options),
    description: draft.description.trim() || null,
    sort_order: Number.parseInt(draft.sort_order, 10) || 0,
  };
}

export function CustomFieldsAdmin({
  fields,
  fieldTypes,
  canManage,
}: {
  fields: CustomField[];
  fieldTypes: FieldTypeOption[];
  canManage: boolean;
}) {
  const t = useTranslations("Settings.customFields");
  const [rows, setRows] = useState(fields);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const typeLabel = (code: string) =>
    fieldTypes.find((f) => f.code === code)?.label ?? code;
  const entityLabel = (code: string) =>
    t.has(`entities.${code}`) ? t(`entities.${code}`) : code;

  async function reload() {
    const res = await bff<CustomField[]>("/api/bff/custom-fields");
    if (res.ok) setRows(res.data);
  }

  async function submit() {
    setError(null);
    setMessage(null);
    if (!draft.label.trim()) {
      setError(t("labelRequired"));
      return;
    }
    if (editingId === null && !KEY_PATTERN.test(draft.key.trim())) {
      setError(t("keyInvalid"));
      return;
    }
    if (
      draft.field_type === "choice" &&
      splitList(draft.options).length === 0
    ) {
      setError(t("optionsRequired"));
      return;
    }
    setBusy(true);
    const res =
      editingId === null
        ? await bff<CustomField>("/api/bff/custom-fields", {
            method: "POST",
            body: JSON.stringify({
              entity_type: draft.entity_type,
              key: draft.key.trim(),
              field_type: draft.field_type,
              ...body(draft),
            }),
          })
        : await bff<CustomField>(`/api/bff/custom-fields/${editingId}`, {
            method: "PATCH",
            body: JSON.stringify(body(draft)),
          });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setMessage(t("saved"));
    setDraft(EMPTY);
    setEditingId(null);
    await reload();
  }

  async function remove(field: CustomField) {
    if (!window.confirm(t("confirmDelete", { label: field.label }))) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/custom-fields/${field.id}`, {
      method: "DELETE",
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setMessage(t("deleted"));
    if (editingId === field.id) {
      setEditingId(null);
      setDraft(EMPTY);
    }
    await reload();
  }

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));
  const grouped = ENTITY_TYPES.map((entity) => ({
    entity,
    list: rows.filter((r) => r.entity_type === entity),
  })).filter((g) => g.list.length > 0);
  const numeric = ["integer", "number", "amount"].includes(draft.field_type);
  const textual = ["string", "text", "rich_text", "url"].includes(
    draft.field_type,
  );

  return (
    <div className="flex flex-col gap-4" data-testid="custom-fields-admin">
      <section className={ui.card} aria-labelledby="custom-fields-list">
        <h2 id="custom-fields-list" className={ui.h2}>
          {t("listTitle")}
        </h2>
        {grouped.length === 0 ? (
          <p className={`mt-2 ${ui.help}`}>{t("empty")}</p>
        ) : (
          grouped.map((g) => (
            <div key={g.entity} className="mt-3">
              <h3 className="text-sm font-semibold">{entityLabel(g.entity)}</h3>
              <div className={ui.tableScroll}>
                <table
                  className={ui.table}
                  data-testid={`custom-fields-${g.entity}`}
                >
                  <thead>
                    <tr>
                      <th>{t("colLabel")}</th>
                      <th>{t("colKey")}</th>
                      <th>{t("colType")}</th>
                      <th>{t("colGroup")}</th>
                      <th>{t("colRequired")}</th>
                      <th>{t("colMain")}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {g.list.map((f) => (
                      <tr key={f.id}>
                        <td>{f.label}</td>
                        <td>
                          <code className="text-xs">{f.key}</code>
                        </td>
                        <td>{typeLabel(f.field_type)}</td>
                        <td>{f.group ?? ""}</td>
                        <td>{f.required ? t("yes") : t("no")}</td>
                        <td>{f.visible_in_main ? t("yes") : t("no")}</td>
                        <td className="whitespace-nowrap">
                          {canManage ? (
                            <span className="flex gap-1">
                              <button
                                type="button"
                                className={ui.buttonSm}
                                disabled={busy}
                                onClick={() => {
                                  setEditingId(f.id);
                                  setDraft(toDraft(f));
                                  setMessage(null);
                                  setError(null);
                                }}
                              >
                                {t("edit")}
                              </button>
                              <button
                                type="button"
                                className={ui.buttonSm}
                                disabled={busy}
                                onClick={() => void remove(f)}
                              >
                                {t("delete")}
                              </button>
                            </span>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))
        )}
      </section>
      {canManage ? (
        <section className={ui.card} aria-labelledby="custom-fields-form">
          <h2 id="custom-fields-form" className={ui.h2}>
            {editingId === null
              ? t("createTitle")
              : t("editTitle", { label: draft.label })}
          </h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("entity")}</span>
              <select
                className={ui.input}
                value={draft.entity_type}
                disabled={busy || editingId !== null}
                onChange={(e) => set("entity_type", e.target.value)}
              >
                {ENTITY_TYPES.map((e) => (
                  <option key={e} value={e}>
                    {entityLabel(e)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("key")}</span>
              <input
                className={ui.input}
                value={draft.key}
                maxLength={63}
                disabled={busy || editingId !== null}
                onChange={(e) => set("key", e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("label")}</span>
              <input
                className={ui.input}
                value={draft.label}
                maxLength={200}
                disabled={busy}
                onChange={(e) => set("label", e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("fieldType")}</span>
              <select
                className={ui.input}
                value={draft.field_type}
                disabled={busy || editingId !== null}
                onChange={(e) => set("field_type", e.target.value)}
              >
                {fieldTypes.map((f) => (
                  <option key={f.code} value={f.code}>
                    {f.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("group")}</span>
              <input
                className={ui.input}
                value={draft.group}
                maxLength={100}
                disabled={busy}
                onChange={(e) => set("group", e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("uniqueness")}</span>
              <select
                className={ui.input}
                value={draft.uniqueness}
                disabled={busy}
                onChange={(e) => set("uniqueness", e.target.value)}
              >
                {UNIQUENESS.map((u) => (
                  <option key={u} value={u}>
                    {t(`uniquenessValues.${u}`)}
                  </option>
                ))}
              </select>
            </label>
            <fieldset className="flex flex-col gap-1">
              <legend className={ui.label}>{t("managementTypes")}</legend>
              <div className="flex flex-wrap gap-3 text-sm">
                {MANAGEMENT_TYPES.map((m) => (
                  <label key={m} className="flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={draft.valid_for_management_types.includes(m)}
                      disabled={busy}
                      onChange={(e) =>
                        set(
                          "valid_for_management_types",
                          e.target.checked
                            ? [...draft.valid_for_management_types, m]
                            : draft.valid_for_management_types.filter(
                                (x) => x !== m,
                              ),
                        )
                      }
                    />
                    {t(`managementTypeValues.${m}`)}
                  </label>
                ))}
              </div>
              <span className={ui.help}>{t("managementTypesHelp")}</span>
            </fieldset>
            <div className="flex flex-col gap-1">
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("contractKinds")}</span>
                <input
                  className={ui.input}
                  value={draft.valid_for_contract_kinds}
                  disabled={busy}
                  onChange={(e) =>
                    set("valid_for_contract_kinds", e.target.value)
                  }
                />
              </label>
              <span className={ui.help}>{t("listHelp")}</span>
            </div>
            {draft.field_type === "choice" ? (
              <div className="flex flex-col gap-1">
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("options")}</span>
                  <input
                    className={ui.input}
                    value={draft.options}
                    disabled={busy}
                    onChange={(e) => set("options", e.target.value)}
                  />
                </label>
                <span className={ui.help}>{t("listHelp")}</span>
              </div>
            ) : null}
            {numeric || textual ? (
              <>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>
                    {numeric ? t("min") : t("minLength")}
                  </span>
                  <input
                    className={ui.input}
                    inputMode="decimal"
                    value={draft.min_value}
                    disabled={busy}
                    onChange={(e) => set("min_value", e.target.value)}
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>
                    {numeric ? t("max") : t("maxLength")}
                  </span>
                  <input
                    className={ui.input}
                    inputMode="decimal"
                    value={draft.max_value}
                    disabled={busy}
                    onChange={(e) => set("max_value", e.target.value)}
                  />
                </label>
              </>
            ) : null}
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("defaultValue")}</span>
              <input
                className={ui.input}
                value={draft.default_value}
                disabled={busy}
                onChange={(e) => set("default_value", e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("sortOrder")}</span>
              <input
                className={ui.input}
                type="number"
                value={draft.sort_order}
                disabled={busy}
                onChange={(e) => set("sort_order", e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 sm:col-span-2 lg:col-span-3">
              <span className={ui.label}>{t("description")}</span>
              <textarea
                className={ui.input}
                rows={2}
                value={draft.description}
                maxLength={2000}
                disabled={busy}
                onChange={(e) => set("description", e.target.value)}
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.required}
                disabled={busy}
                onChange={(e) => set("required", e.target.checked)}
              />
              {t("required")}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.visible_in_main}
                disabled={busy}
                onChange={(e) => set("visible_in_main", e.target.checked)}
              />
              {t("visibleInMain")}
            </label>
          </div>
          <div className={`mt-3 ${ui.formActions}`}>
            <button
              type="button"
              className={ui.primary}
              disabled={busy}
              onClick={() => void submit()}
            >
              {editingId === null ? t("create") : t("save")}
            </button>
            {editingId !== null ? (
              <button
                type="button"
                className={ui.secondary}
                disabled={busy}
                onClick={() => {
                  setEditingId(null);
                  setDraft(EMPTY);
                }}
              >
                {t("cancel")}
              </button>
            ) : null}
          </div>
          <p className={`mt-2 ${ui.help}`}>{t("immutableHint")}</p>
        </section>
      ) : (
        <p className={ui.help}>{t("readOnly")}</p>
      )}
      {message ? (
        <span className="text-xs text-success-fg">{message}</span>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
