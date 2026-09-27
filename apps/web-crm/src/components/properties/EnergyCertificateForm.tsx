"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Energieausweis des Gebäudes (4.3, A63). Die Felder liegen seit AP2 am Gebäude, nicht mehr am
 *  Objekt. */
export type EnergyCertificate = {
  energy_certificate_law: string | null;
  energy_certificate_type: string | null;
  energy_final_heat_kwh: string | null;
  energy_hot_water_included: boolean;
  energy_final_electricity_kwh: string | null;
  heating_type_code: string | null;
  energy_sources: string[];
  energy_certificate_class: string | null;
  energy_certificate_construction_year: number | null;
  energy_certificate_issued_on: string | null;
  energy_certificate_valid_until: string | null;
};

export type EnergyBuilding = Partial<EnergyCertificate> & { id: string; version: number; name?: string };

const TEXT_KEYS = [
  "energy_certificate_law",
  "energy_certificate_type",
  "energy_final_heat_kwh",
  "energy_final_electricity_kwh",
  "heating_type_code",
  "energy_sources",
  "energy_certificate_class",
  "energy_certificate_construction_year",
  "energy_certificate_issued_on",
  "energy_certificate_valid_until",
] as const;

type Key = (typeof TEXT_KEYS)[number];
type Form = Record<Key, string> & { energy_hot_water_included: boolean };

function toForm(building: EnergyBuilding): Form {
  const out = {} as Form;
  for (const key of TEXT_KEYS) {
    const value = building[key];
    out[key] = value == null ? "" : Array.isArray(value) ? value.join(", ") : String(value);
  }
  out.energy_hot_water_included = building.energy_hot_water_included === true;
  return out;
}

/** Werte werden aus dem Ausweis übernommen, nichts wird abgeleitet. Gespeichert wird über
 *  PATCH /buildings/{id} (nur die Ausweisfelder, If-Match aus `version`); die Antwort liefert die
 *  neue Version, danach wird die Seite aktualisiert. Ohne Schreibrecht ist das Formular lesend. */
export function EnergyCertificateForm({ building, canEdit = true }: { building: EnergyBuilding; canEdit?: boolean }) {
  const t = useTranslations("Properties.energyCertificate");
  const router = useRouter();
  const [form, setForm] = useState<Form>(toForm(building));
  const [version, setVersion] = useState(building.version);
  // Other sections of the same page (inline master data, ADR 0012) bump the version and refresh
  // the server component; without taking over the new prop the next save would hit 412.
  useEffect(() => {
    setVersion(building.version);
  }, [building.version]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const set = (key: Key) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setSaved(false);
    setForm((f) => ({ ...f, [key]: e.target.value }));
  };

  const validate = (): string | null => {
    for (const key of ["energy_final_heat_kwh", "energy_final_electricity_kwh"] as const) {
      const value = form[key].trim();
      if (value && !/^\d+([.,]\d{1,2})?$/.test(value)) return t("errors.value");
    }
    const year = form.energy_certificate_construction_year.trim();
    if (year && !/^\d{4}$/.test(year)) return t("errors.year");
    const issued = form.energy_certificate_issued_on;
    const until = form.energy_certificate_valid_until;
    if (issued && until && until < issued) return t("errors.validUntil");
    return null;
  };

  const save = async () => {
    setError(null);
    setSaved(false);
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    const body: Record<string, unknown> = { energy_hot_water_included: form.energy_hot_water_included };
    for (const key of TEXT_KEYS) {
      const value = form[key].trim();
      if (key === "energy_sources") {
        body[key] = value === "" ? [] : value.split(",").map((s) => s.trim()).filter(Boolean);
      } else if (value === "") {
        body[key] = null;
      } else if (key === "energy_certificate_construction_year") {
        body[key] = Number(value);
      } else if (key === "energy_final_heat_kwh" || key === "energy_final_electricity_kwh") {
        body[key] = value.replace(",", ".");
      } else if (key === "energy_certificate_class") {
        body[key] = value.toUpperCase();
      } else {
        body[key] = value;
      }
    }
    const res = await bff<{ version?: number }>(`/api/bff/buildings/${building.id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
      headers: { "If-Match": String(version) },
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    if (res.data?.version != null) setVersion(res.data.version);
    setSaved(true);
    router.refresh();
  };

  const ro = !canEdit;
  return (
    <section className={ui.card} data-testid="energy-certificate" data-version={version}>
      <h2 className={ui.subtitle}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{building.name ? t("buildingHint", { name: building.name }) : t("help")}</p>
      <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("law")}</span>
          <select className={ui.input} value={form.energy_certificate_law} onChange={set("energy_certificate_law")} disabled={ro}>
            <option value="">{t("none")}</option>
            <option value="geg">{t("laws.geg")}</option>
            <option value="enev_2014">{t("laws.enev_2014")}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("type")}</span>
          <select className={ui.input} value={form.energy_certificate_type} onChange={set("energy_certificate_type")} disabled={ro}>
            <option value="">{t("none")}</option>
            <option value="verbrauch">{t("types.verbrauch")}</option>
            <option value="bedarf">{t("types.bedarf")}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("finalHeat")}</span>
          <input className={ui.input} inputMode="decimal" value={form.energy_final_heat_kwh} onChange={set("energy_final_heat_kwh")} readOnly={ro} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("finalElectricity")}</span>
          <input className={ui.input} inputMode="decimal" value={form.energy_final_electricity_kwh} onChange={set("energy_final_electricity_kwh")} readOnly={ro} />
        </label>
        <label className="flex items-center gap-2 self-end text-sm">
          <input
            type="checkbox"
            checked={form.energy_hot_water_included}
            disabled={ro}
            onChange={(e) => {
              setSaved(false);
              setForm((f) => ({ ...f, energy_hot_water_included: e.target.checked }));
            }}
          />
          {t("hotWaterIncluded")}
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("heatingType")}</span>
          <select className={ui.input} value={form.heating_type_code} onChange={set("heating_type_code")} disabled={ro}>
            <option value="">{t("none")}</option>
            <option value="zentral">{t("heatingTypes.zentral")}</option>
            <option value="etage">{t("heatingTypes.etage")}</option>
            <option value="ofen">{t("heatingTypes.ofen")}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("sources")}</span>
          <input className={ui.input} value={form.energy_sources} onChange={set("energy_sources")} readOnly={ro} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("constructionYear")}</span>
          <input className={ui.input} inputMode="numeric" value={form.energy_certificate_construction_year} onChange={set("energy_certificate_construction_year")} readOnly={ro} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("issuedOn")}</span>
          <input type="date" className={ui.input} value={form.energy_certificate_issued_on} onChange={set("energy_certificate_issued_on")} readOnly={ro} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("validUntil")}</span>
          <input type="date" className={ui.input} value={form.energy_certificate_valid_until} onChange={set("energy_certificate_valid_until")} readOnly={ro} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("class")}</span>
          <input className={ui.input} maxLength={4} value={form.energy_certificate_class} onChange={set("energy_certificate_class")} readOnly={ro} />
        </label>
        {canEdit ? (
          <div className="flex items-end gap-2">
            <button type="button" className={ui.primary} disabled={busy} onClick={save}>
              {t("save")}
            </button>
            {saved ? (
              <span role="status" className="text-sm text-success-fg">
                {t("saved")}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
