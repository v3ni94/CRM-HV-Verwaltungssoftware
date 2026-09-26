"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type { PortalForm, PortalFormField } from "@/components/portal/types";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Values = Record<string, string>;
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
      const filled = field.type === "file" ? (files[field.key]?.length ?? 0) > 0 : (values[field.key] ?? "").trim().length > 0;
      if (field.required && !filled) {
        setError(t("requiredMissing", { label: field.label }));
        return;
      }
    }
    setBusy(true);
    const payload: Record<string, string | string[]> = {};
    for (const field of form.fields) {
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
      } else {
        const value = (values[field.key] ?? "").trim();
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
        <div key={field.key}>
          <label htmlFor={fieldId(field)} className={ui.label}>
            {field.label}
            {field.required ? " *" : ""}
          </label>
          {field.type === "select" ? (
            <select
              id={fieldId(field)}
              className={ui.input}
              aria-required={field.required || undefined}
              value={values[field.key] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [field.key]: e.target.value }))}
            >
              <option value="">{t("choose")}</option>
              {(field.options ?? []).map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          ) : field.type === "file" ? (
            <input
              id={fieldId(field)}
              type="file"
              aria-required={field.required || undefined}
              multiple
              accept="image/jpeg,image/png,application/pdf"
              className={ui.input}
              onChange={(e) => setFiles((f) => ({ ...f, [field.key]: Array.from(e.target.files ?? []) }))}
            />
          ) : (
            <input
              id={fieldId(field)}
              type={field.type === "date" ? "date" : field.type === "number" ? "number" : "text"}
              step={field.type === "number" ? "any" : undefined}
              aria-required={field.required || undefined}
              className={ui.input}
              value={values[field.key] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [field.key]: e.target.value }))}
            />
          )}
        </div>
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
