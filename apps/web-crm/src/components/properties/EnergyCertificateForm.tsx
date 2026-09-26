"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type EnergyCertificate = {
  energy_certificate_type: string | null;
  energy_certificate_value: string | null;
  energy_certificate_source: string | null;
  energy_certificate_construction_year: number | null;
  energy_certificate_issued_on: string | null;
  energy_certificate_valid_until: string | null;
  energy_certificate_class: string | null;
};

const KEYS = [
  "energy_certificate_type",
  "energy_certificate_value",
  "energy_certificate_source",
  "energy_certificate_construction_year",
  "energy_certificate_issued_on",
  "energy_certificate_valid_until",
  "energy_certificate_class",
] as const;

type Key = (typeof KEYS)[number];
type Form = Record<Key, string>;

function toForm(property: Record<string, unknown>): Form {
  const out = {} as Form;
  for (const key of KEYS) {
    const value = property[key];
    out[key] = value == null ? "" : String(value);
  }
  return out;
}

/** Energieausweis am Objekt (A63): Werte werden aus dem Ausweis übernommen, nichts wird
 *  abgeleitet. Gespeichert wird über PUT /properties/{id} mit den vollständigen Stammdaten,
 *  daher erhält die Komponente den kompletten Objektdatensatz. */
export function EnergyCertificateForm({ property }: { property: Record<string, unknown> & { id: string; version: number } }) {
  const t = useTranslations("Properties.energyCertificate");
  const router = useRouter();
  const [form, setForm] = useState<Form>(toForm(property));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const set = (key: Key) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setSaved(false);
    setForm((f) => ({ ...f, [key]: e.target.value }));
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(property)) {
      if (!["id", "status", "version", "legal_entities"].includes(key)) body[key] = value;
    }
    for (const key of KEYS) {
      const value = form[key].trim();
      body[key] = value === "" ? null : key === "energy_certificate_construction_year" ? Number(value) : value;
    }
    const res = await bff(`/api/bff/properties/${property.id}`, {
      method: "PUT",
      body: JSON.stringify(body),
      headers: { "If-Match": String(property.version) },
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setSaved(true);
    router.refresh();
  };

  return (
    <section className={ui.card} data-testid="energy-certificate">
      <h2 className={ui.subtitle}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("help")}</p>
      <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("type")}</span>
          <select className={ui.input} value={form.energy_certificate_type} onChange={set("energy_certificate_type")}>
            <option value="">{t("none")}</option>
            <option value="verbrauch">{t("types.verbrauch")}</option>
            <option value="bedarf">{t("types.bedarf")}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("value")}</span>
          <input className={ui.input} inputMode="decimal" value={form.energy_certificate_value} onChange={set("energy_certificate_value")} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("source")}</span>
          <input className={ui.input} value={form.energy_certificate_source} onChange={set("energy_certificate_source")} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("constructionYear")}</span>
          <input className={ui.input} inputMode="numeric" value={form.energy_certificate_construction_year} onChange={set("energy_certificate_construction_year")} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("issuedOn")}</span>
          <input type="date" className={ui.input} value={form.energy_certificate_issued_on} onChange={set("energy_certificate_issued_on")} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("validUntil")}</span>
          <input type="date" className={ui.input} value={form.energy_certificate_valid_until} onChange={set("energy_certificate_valid_until")} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("class")}</span>
          <input className={ui.input} maxLength={4} value={form.energy_certificate_class} onChange={set("energy_certificate_class")} />
        </label>
        <div className="flex items-end gap-2">
          <button type="button" className={ui.primary} disabled={busy} onClick={save}>
            {t("save")}
          </button>
          {saved ? <span className="text-sm text-muted">{t("saved")}</span> : null}
        </div>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
