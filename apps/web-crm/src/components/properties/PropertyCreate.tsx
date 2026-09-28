"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { EntryHints } from "@/components/common/EntryHints";
import { bff } from "@/lib/bff";
import { checkProperty } from "@/lib/entry-standards";
import { ui } from "@/lib/ui";

const EMPTY = { number: "", name: "", management_type: "hoa", street: "", house_number: "", postal_code: "", city: "", state: "" };

/** New property (M4). The management type fixes the legal entities and cannot change later. */
export function PropertyCreate() {
  const t = useTranslations("Properties");
  const router = useRouter();
  const [f, setF] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF((p) => ({ ...p, [k]: e.target.value }));
  // Entry standards (ES-01 to ES-04): only an invalid German postcode blocks, the rest are hints.
  const touched = [f.name, f.street, f.house_number, f.postal_code, f.city].some((v) => v.trim() !== "");
  const findings = touched ? checkProperty(f) : [];
  const valid = /^\d{3}$/.test(f.number) && f.name.trim().length >= 2 && !findings.some((x) => x.severity === "error");
  const submit = async () => {
    setBusy(true);
    setError(null);
    const body: Record<string, string> = { number: f.number, name: f.name.trim(), management_type: f.management_type };
    for (const k of ["street", "house_number", "postal_code", "city", "state"] as const) {
      if (f[k].trim()) body[k] = f[k].trim();
    }
    const res = await bff<{ id: string }>("/api/bff/properties", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) router.push(`/objekte/${res.data.id}`);
    else setError(res.message);
  };
  const field = (k: keyof typeof f) => (
    <label className="flex flex-col gap-1">
      <span className={ui.label}>{t(`fields.${k}`)}</span>
      <input className={ui.input} value={f[k]} onChange={set(k)} placeholder={k === "name" ? t("namePlaceholder") : undefined} inputMode={k === "postal_code" ? "numeric" : undefined} />
    </label>
  );
  return (
    <details className={ui.card}>
      <summary className="cursor-pointer text-sm font-medium">{t("create")}</summary>
      <div className="mt-4 grid gap-3 sm:grid-cols-4">
        {field("number")}
        {field("name")}
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("fields.management_type")}</span>
          <select className={ui.input} value={f.management_type} onChange={set("management_type")}>
            {["hoa", "rental", "hoa_with_sev"].map((m) => (
              <option key={m} value={m}>
                {t(`managementType.${m}`)}
              </option>
            ))}
          </select>
        </label>
        {field("street")}
        {field("house_number")}
        {field("postal_code")}
        {field("city")}
        {field("state")}
      </div>
      <p className="mt-2 text-xs text-muted">{t("createHint")}</p>
      <div className="mt-2">
        <EntryHints findings={findings} testId="property-create-hints" onApplySuggestion={(name) => setF((p) => ({ ...p, name }))} />
      </div>
      <button type="button" className={`${ui.primary} ${ui.actionFull} mt-3`} disabled={busy || !valid} onClick={submit}>
        {t("createButton")}
      </button>
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
    </details>
  );
}
