"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type { PortalForm, PortalFormField } from "@/components/portal/types";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Values = Record<string, string | string[]>;
type Files = Record<string, File[]>;

/** Ein Formular der Verwaltung (A56): Felder aus der Vorlage, Pflichtfelder werden vor dem
 *  Senden geprüft, Dateien werden zuerst hochgeladen (nur eigene Uploads) und dann mit der
 *  Einreichung verknüpft. Die Einreichung wird ein Vorgang bei der Verwaltung (Ticket). */
function FormCard({ form, onDone }: { form: PortalForm; onDone: () => void }) {
  const t = useTranslations("Forms");
  const [values, setValues] = useState<Values>({});
  const [files, setFiles] = useState<Files>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Keyboard: the opening button is replaced by the form, so focus moves to its heading.
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  function fieldId(field: PortalFormField) {
    return `form-${form.id}-${field.key}`;
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    for (const field of form.fields) {
      if (field.type === "heading" || field.type === "info") continue;
      const raw = values[field.key];
      const filled =
        field.type === "file"
          ? (files[field.key]?.length ?? 0) > 0
          : field.type === "multiselect"
            ? Array.isArray(raw) && raw.length > 0
            : field.type === "checkbox"
              ? raw === "true"
              : typeof raw === "string" && raw.trim().length > 0;
      if (field.required && !filled) {
        setError(t("requiredMissing", { label: field.label }));
        return;
      }
    }
    setBusy(true);
    const payload: Record<string, string | string[]> = {};
    for (const field of form.fields) {
      if (field.type === "heading" || field.type === "info") continue;
      if (field.type === "file") {
        const ids: string[] = [];
        for (const file of files[field.key] ?? []) {
          const body = new FormData();
          body.append("file", file);
          const upload = await bff<{ id: string }>("/api/bff/portal/uploads", { method: "POST", body });
          if (!upload.ok) {
            setBusy(false);
            setError(upload.message);
            return;
          }
          ids.push(upload.data.id);
        }
        if (ids.length > 0) payload[field.key] = ids;
      } else if (field.type === "multiselect") {
        const chosen = values[field.key];
        if (Array.isArray(chosen) && chosen.length > 0) payload[field.key] = chosen;
      } else if (field.type === "checkbox") {
        payload[field.key] = values[field.key] === "true" ? "true" : "false";
      } else {
        const raw = values[field.key];
        const value = typeof raw === "string" ? raw.trim() : "";
        if (value) payload[field.key] = value;
      }
    }
    const result = await bff<{ ticket_number: number }>(`/api/bff/portal/forms/${form.id}/submissions`, {
      method: "POST",
      body: JSON.stringify({ values: payload }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setValues({});
    setFiles({});
    onDone();
  }

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      aria-busy={busy}
      className={`${ui.card} flex flex-col gap-3`}
      aria-label={form.name}
      data-testid="portal-form"
    >
      <h2 ref={headingRef} tabIndex={-1} className={`${ui.h2} focus:outline-none`}>
        {form.name}
      </h2>
      {form.description ? <p className="text-sm text-muted">{form.description}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {form.fields.some((field) => field.required) ? <p className={ui.help}>{t("requiredHint")}</p> : null}
      {form.fields.map((field) => (
        <FormElement
          key={field.key}
          field={field}
          id={fieldId(field)}
          value={values[field.key]}
          onChange={(value) => setValues((v) => ({ ...v, [field.key]: value }))}
          onFiles={(list) => setFiles((f) => ({ ...f, [field.key]: list }))}
        />
      ))}
      <p className={ui.help}>{t("proposalNote")}</p>
      <div className={ui.formActions}>
        <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
          {busy ? t("submitting") : t("submit")}
        </button>
      </div>
    </form>
  );
}

/** Ein Element der Vorlage (SA-03): Eingabetypen plus Überschrift und Hinweistext. */
function FormElement({
  field,
  id,
  value,
  onChange,
  onFiles,
}: {
  field: PortalFormField;
  id: string;
  value: string | string[] | undefined;
  onChange: (value: string | string[]) => void;
  onFiles: (files: File[]) => void;
}) {
  const t = useTranslations("Forms");
  const text = typeof value === "string" ? value : "";
  const required = field.required || undefined;
  if (field.type === "heading") return <h3 className="text-base font-semibold">{field.label}</h3>;
  if (field.type === "info") {
    return (
      <p className="text-sm text-muted">
        {field.label}
        {field.help ? ` ${field.help}` : ""}
      </p>
    );
  }
  const help = field.help ? <p className={ui.help}>{field.help}</p> : null;
  if (field.type === "checkbox") {
    return (
      <div>
        <label htmlFor={id} className="flex items-start gap-2 text-sm">
          <input id={id} type="checkbox" aria-required={required} checked={text === "true"} onChange={(e) => onChange(e.target.checked ? "true" : "")} />
          <span>
            {field.label}
            {field.required ? " *" : ""}
          </span>
        </label>
        {help}
      </div>
    );
  }
  if (field.type === "radio" || field.type === "multiselect") {
    const chosen = Array.isArray(value) ? value : [];
    return (
      <fieldset>
        <legend className={ui.label}>
          {field.label}
          {field.required ? " *" : ""}
        </legend>
        <div className="flex flex-col gap-1">
          {(field.options ?? []).map((option) => (
            <label key={option} className="flex items-center gap-2 text-sm">
              <input
                type={field.type === "radio" ? "radio" : "checkbox"}
                name={id}
                checked={field.type === "radio" ? text === option : chosen.includes(option)}
                onChange={(e) =>
                  field.type === "radio"
                    ? onChange(option)
                    : onChange(e.target.checked ? [...chosen, option] : chosen.filter((o) => o !== option))
                }
              />
              {option}
            </label>
          ))}
        </div>
        {help}
      </fieldset>
    );
  }
  return (
    <div>
      <label htmlFor={id} className={ui.label}>
        {field.label}
        {field.required ? " *" : ""}
      </label>
      {field.type === "select" ? (
        <select id={id} className={ui.input} aria-required={required} value={text} onChange={(e) => onChange(e.target.value)}>
          <option value="">{t("choose")}</option>
          {(field.options ?? []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      ) : field.type === "file" ? (
        <input
          id={id}
          type="file"
          aria-required={required}
          multiple
          accept="image/jpeg,image/png,application/pdf"
          className={ui.input}
          onChange={(e) => onFiles(Array.from(e.target.files ?? []))}
        />
      ) : field.type === "textarea" ? (
        <textarea id={id} rows={4} aria-required={required} className={ui.input} value={text} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input
          id={id}
          type={
            field.type === "date"
              ? "date"
              : field.type === "time"
                ? "time"
                : field.type === "number"
                  ? "number"
                  : field.type === "email"
                    ? "email"
                    : field.type === "phone"
                      ? "tel"
                      : "text"
          }
          step={field.type === "number" ? "any" : undefined}
          aria-required={required}
          className={ui.input}
          value={text}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {help}
    </div>
  );
}

export function PortalForms({ forms }: { forms: PortalForm[] }) {
  const t = useTranslations("Forms");
  const router = useRouter();
  const [open, setOpen] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  if (forms.length === 0) return <p className={ui.notice}>{t("empty")}</p>;
  return (
    <div className={ui.sectionGap}>
      {done ? (
        <p className={ui.success} role="status">
          {t("submitted", { name: done })}
        </p>
      ) : null}
      <ul className="flex flex-col gap-3">
        {forms.map((form) => (
          <li key={form.id}>
            {open === form.id ? (
              <FormCard
                form={form}
                onDone={() => {
                  setOpen(null);
                  setDone(form.name);
                  router.refresh();
                }}
              />
            ) : (
              <button type="button" className={`${ui.cardLink} w-full text-left`} aria-expanded="false" onClick={() => setOpen(form.id)}>
                <span className="font-medium">{form.name}</span>
                {form.description ? <span className="mt-1 block text-sm text-muted">{form.description}</span> : null}
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
