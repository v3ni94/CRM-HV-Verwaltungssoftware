"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Company = components["schemas"]["CompanyData"];
type Branding = components["schemas"]["Branding"];

const FIELDS: (keyof Company)[] = [
  "name",
  "legal_form",
  "street",
  "postal_code",
  "city",
  "country",
  "register_court",
  "register_number",
  "vat_id",
  "phone",
  "email",
  "website",
  "management_title",
];

export function CompanySettings({ initial, branding, canUpdate }: { initial: Company; branding: Branding; canUpdate: boolean }) {
  const t = useTranslations("CompanySettings");
  const [values, setValues] = useState<Company>(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function set(field: keyof Company, value: string) {
    setValues((prev) => ({ ...prev, [field]: value }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ company: Company }>("/api/bff/tenant/settings", {
      method: "PATCH",
      body: JSON.stringify({ company: values }),
    });
    setBusy(false);
    if (res.ok) setMessage(t("saved"));
    else setError(res.message);
  }

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={(e) => void submit(e)} className={`${ui.card} grid gap-3 sm:grid-cols-2`}>
        {FIELDS.map((field) => (
          <label key={field} className="flex flex-col gap-1">
            <span className={ui.label}>{t(`field.${field}`)}</span>
            <input
              className={ui.input}
              value={values[field] ?? ""}
              disabled={!canUpdate}
              onChange={(e) => set(field, e.target.value)}
            />
          </label>
        ))}
        {canUpdate ? (
          <div className="sm:col-span-2 flex items-center gap-2">
            <button type="submit" className={ui.primary} disabled={busy}>
              {t("save")}
            </button>
            {message ? <span className="text-xs text-success-fg">{message}</span> : null}
            {error ? <span className={ui.error}>{error}</span> : null}
          </div>
        ) : (
          <p className="sm:col-span-2 text-xs text-muted">{t("readOnly")}</p>
        )}
      </form>
      <section className={ui.card}>
        <h2 className="text-sm font-semibold">{t("brandingTitle")}</h2>
        <p className="mt-1 text-xs text-muted">{t("brandingHint")}</p>
        <div className="mt-2 flex flex-wrap gap-3 text-sm">
          <span className="flex items-center gap-2">
            <span
              className="inline-block h-4 w-4 rounded-full border border-border"
              style={{ background: branding.primary_color ?? undefined }}
            />
            {t("field.primaryColor")}: {branding.primary_color ?? "-"}
          </span>
          <span className="flex items-center gap-2">
            <span
              className="inline-block h-4 w-4 rounded-full border border-border"
              style={{ background: branding.accent_color ?? undefined }}
            />
            {t("field.accentColor")}: {branding.accent_color ?? "-"}
          </span>
        </div>
      </section>
    </div>
  );
}
