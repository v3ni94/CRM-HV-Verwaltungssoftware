"use client";

import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import type { PortalFormField } from "@/components/settings/PortalFormsAdmin";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Values = Record<string, string | string[]>;
type PreviewResult = {
  valid: boolean;
  errors: { field: string; message: string }[];
  rendered: string | null;
};

const DISPLAY = ["heading", "info", "divider"];
const isCheck = (type: string) => type === "checkbox" || type === "consent";

function inputType(type: string): string {
  switch (type) {
    case "date":
      return "date";
    case "time":
      return "time";
    case "number":
      return "number";
    case "email":
      return "email";
    case "phone":
      return "tel";
    default:
      return "text";
  }
}

function PreviewElement({
  field,
  id,
  value,
  error,
  onChange,
}: {
  field: PortalFormField;
  id: string;
  value: string | string[] | undefined;
  error: string | undefined;
  onChange: (value: string | string[]) => void;
}) {
  const t = useTranslations("PortalFormPreview");
  const text = typeof value === "string" ? value : "";
  const chosen = Array.isArray(value) ? value : [];
  const mark = field.required ? " *" : "";
  const help = field.help ? <p className={ui.help}>{field.help}</p> : null;
  const problem = error ? (
    <p id={`${id}-error`} role="alert" className={ui.error}>
      {error}
    </p>
  ) : null;
  const described = error ? `${id}-error` : undefined;
  if (field.type === "divider") return <hr className="border-border" />;
  if (field.type === "heading") return <h4 className="text-base font-semibold">{field.label}</h4>;
  if (field.type === "info") {
    return (
      <p className="text-sm text-muted">
        {field.label}
        {field.help ? ` ${field.help}` : ""}
      </p>
    );
  }
  if (isCheck(field.type)) {
    return (
      <div>
        <label htmlFor={id} className="flex items-start gap-2 text-sm">
          <input id={id} type="checkbox" aria-describedby={described} checked={text === "true"} onChange={(e) => onChange(e.target.checked ? "true" : "")} />
          <span>
            {field.label}
            {mark}
          </span>
        </label>
        {help}
        {problem}
      </div>
    );
  }
  if (field.type === "radio" || field.type === "multiselect") {
    return (
      <fieldset>
        <legend className={ui.label}>
          {field.label}
          {mark}
        </legend>
        <div className="flex flex-col gap-1">
          {(field.options ?? []).map((option) => (
            <label key={option} className="flex items-center gap-2 text-sm">
              <input
                type={field.type === "radio" ? "radio" : "checkbox"}
                name={id}
                checked={field.type === "radio" ? text === option : chosen.includes(option)}
                onChange={(e) =>
                  field.type === "radio" ? onChange(option) : onChange(e.target.checked ? [...chosen, option] : chosen.filter((o) => o !== option))
                }
              />
              {option}
            </label>
          ))}
        </div>
        {help}
        {problem}
      </fieldset>
    );
  }
  return (
    <div>
      <label htmlFor={id} className={ui.label}>
        {field.label}
        {mark}
      </label>
      {field.type === "select" ? (
        <select id={id} className={ui.input} aria-describedby={described} value={text} onChange={(e) => onChange(e.target.value)}>
          <option value="">{t("choose")}</option>
          {(field.options ?? []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      ) : field.type === "file" ? (
        <>
          <input id={id} type="file" disabled className={ui.input} />
          <p className={ui.help}>{t("fileNote")}</p>
        </>
      ) : field.type === "textarea" || field.type === "address" ? (
        <textarea id={id} rows={4} aria-describedby={described} className={ui.input} value={text} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input
          id={id}
          type={inputType(field.type)}
          step={field.type === "number" ? "any" : undefined}
          inputMode={field.type === "amount" ? "decimal" : undefined}
          aria-describedby={described}
          className={ui.input}
          value={text}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {help}
      {problem}
    </div>
  );
}

/** Vorschau des Formularbaukastens (AA14-01): zeigt die Felder wie im Portal und prüft
 *  Beispielwerte im Trockenlauf mit denselben Regeln wie die Einreichung im Portal
 *  (POST /portal-admin/forms/preview). Es wird nichts gespeichert, kein Ticket angelegt und
 *  nichts versendet; Dateien werden in der Vorschau nicht hochgeladen. */
export function PortalFormPreview({ name, fields }: { name: string; fields: PortalFormField[] }) {
  const t = useTranslations("PortalFormPreview");
  const base = useId();
  const [values, setValues] = useState<Values>({});
  const [result, setResult] = useState<PreviewResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const errorByKey = new Map((result?.errors ?? []).map((e) => [e.field.replace(/^values\./, ""), e.message]));

  async function check() {
    setBusy(true);
    setError(null);
    const payload: Values = {};
    for (const field of fields) {
      if (DISPLAY.includes(field.type) || field.type === "file") continue;
      const raw = values[field.key];
      if (isCheck(field.type)) payload[field.key] = raw === "true" ? "true" : "false";
      else if (Array.isArray(raw)) {
        if (raw.length > 0) payload[field.key] = raw;
      } else if (typeof raw === "string" && raw.trim()) payload[field.key] = raw.trim();
    }
    const res = await bff<PreviewResult>("/api/bff/portal-admin/forms/preview", {
      method: "POST",
      body: JSON.stringify({
        name: name.trim() || t("defaultName"),
        fields: fields.map((f) => ({ key: f.key, label: f.label, type: f.type, required: f.required, options: f.options ?? null, help: f.help ?? null })),
        values: payload,
      }),
    });
    setBusy(false);
    if (res.ok) setResult(res.data);
    else {
      setResult(null);
      setError(res.message);
    }
  }

  return (
    <div className={`${ui.card} flex flex-col gap-3`} data-testid="portal-form-preview">
      <h3 className="text-base font-semibold">{t("title")}</h3>
      <p className={ui.help}>{t("intro")}</p>
      {fields.length === 0 ? <p className="text-sm text-muted">{t("noFields")}</p> : null}
      {fields.some((f) => f.required) ? <p className={ui.help}>{t("requiredHint")}</p> : null}
      {fields.map((field) => (
        <PreviewElement
          key={field.key}
          field={field}
          id={`${base}-${field.key}`}
          value={values[field.key]}
          error={errorByKey.get(field.key)}
          onChange={(value) => setValues((v) => ({ ...v, [field.key]: value }))}
        />
      ))}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {result?.valid ? (
        <div role="status" className={ui.success}>
          <p>{t("valid")}</p>
          {result.rendered ? (
            <>
              <p className="mt-2 text-xs font-medium">{t("ticketText")}</p>
              <pre className="mt-1 whitespace-pre-wrap text-sm" data-testid="portal-form-preview-text">
                {result.rendered}
              </pre>
            </>
          ) : null}
        </div>
      ) : null}
      {result && !result.valid ? (
        <p role="status" className={ui.alert}>
          {t("invalid", { count: result.errors.length })}
        </p>
      ) : null}
      <div className={ui.formActions}>
        <button type="button" className={ui.button} disabled={busy || fields.length === 0} onClick={check}>
          {busy ? t("checking") : t("check")}
        </button>
      </div>
    </div>
  );
}
