"use client";
/** Stammdaten des Objekts, an Ort und Stelle editierbar (AP8, ADR 0012): jedes Feld speichert
 *  sich per PATCH /properties/{id} mit If-Match aus `version`. Finanzfelder gehören nicht dazu. */
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { EditableSection } from "@/components/common/EditableSection";
import { EntryHints } from "@/components/common/EntryHints";
import { InlineField, type InlineValue } from "@/components/common/InlineField";
import { useAutosave } from "@/components/common/useAutosave";
import { checkProperty, postcodeInvalid } from "@/lib/entry-standards";
import { formatDecimal } from "@/lib/format";

export type PropertyMaster = {
  id: string;
  version: number;
  name: string;
  street?: string | null;
  house_number?: string | null;
  postal_code?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  municipality_code?: string | null;
  property_type_code?: string | null;
  land_registry_district?: string | null;
  land_registry_sheet?: string | null;
  parcel?: string | null;
  built_area_sqm?: string | null;
  unbuilt_area_sqm?: string | null;
  sealed_area_sqm?: string | null;
  garden_use?: string | null;
  garden_notes?: string | null;
  renovation_flag?: boolean;
  renovation_notes?: string | null;
  allocation_loss_risk_percent?: string | null;
  managed_from?: string | null;
  managed_to?: string | null;
  notes?: string | null;
};

export function nonNegative(message: string) {
  return (value: unknown): string | null => (typeof value === "string" && value !== "" && Number(value.replace(",", ".")) < 0 ? message : null);
}

export function area(value: InlineValue): string {
  return value == null || value === "" ? "" : `${formatDecimal(String(value), 2)} m²`;
}

export function PropertyMasterData({ property, canEdit }: { property: PropertyMaster; canEdit: boolean }) {
  const t = useTranslations("Properties");
  const tm = useTranslations("Properties.masterData");
  const router = useRouter();
  const autosave = useAutosave<PropertyMaster>({ path: `properties/${property.id}`, version: property.version, onSaved: () => router.refresh() });
  const current = { ...property, ...(autosave.data ?? {}) };
  const field = (name: keyof PropertyMaster) => ({ name, value: current[name] as InlineValue, onSave: autosave.save, state: autosave.fieldState(name) });
  const gardenUses = ["none", "yes", "partial"].map((v) => ({ value: v, label: tm(`gardenUses.${v}`) }));
  const areaCheck = nonNegative(tm("invalidArea"));
  const te = useTranslations("EntryStandards");
  // ES-01 is hard (also on the API); the other entry standards are shown as hints only.
  const postcodeCheck = (v: unknown) => (typeof v === "string" && postcodeInvalid(current.country, v) ? te("rules.ES-01") : null);
  const findings = checkProperty(current).filter((f) => f.severity !== "error");
  return (
    <EditableSection
      title={tm("title")}
      description={tm("description")}
      canEdit={canEdit}
      status={autosave.status}
      conflict={autosave.conflict}
      onEditingChange={(editing) => {
        if (!editing) void autosave.flush();
      }}
      testId="property-master-data"
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <InlineField {...field("name")} label={t("fields.name")} required maxLength={200} />
        <InlineField {...field("property_type_code")} label={tm("propertyTypeCode")} type="select" catalog="property_type" />
        <InlineField {...field("street")} label={t("fields.street")} maxLength={200} />
        <InlineField {...field("house_number")} label={t("fields.house_number")} maxLength={20} />
        <InlineField {...field("postal_code")} label={t("fields.postal_code")} maxLength={20} validate={postcodeCheck} />
        <InlineField {...field("city")} label={t("fields.city")} maxLength={100} />
        <InlineField {...field("state")} label={t("fields.state")} />
        <InlineField {...field("municipality_code")} label={tm("municipalityCode")} />
        <InlineField {...field("land_registry_district")} label={tm("landRegistryDistrict")} />
        <InlineField {...field("land_registry_sheet")} label={tm("landRegistrySheet")} />
        <InlineField {...field("parcel")} label={tm("parcel")} />
        <InlineField {...field("built_area_sqm")} label={tm("builtAreaSqm")} type="number" format={area} validate={areaCheck} />
        <InlineField {...field("unbuilt_area_sqm")} label={tm("unbuiltAreaSqm")} type="number" format={area} validate={areaCheck} />
        <InlineField {...field("sealed_area_sqm")} label={tm("sealedAreaSqm")} type="number" format={area} validate={areaCheck} />
        <InlineField {...field("garden_use")} label={tm("gardenUse")} type="select" options={gardenUses} />
        <InlineField {...field("renovation_flag")} label={tm("renovationFlag")} type="boolean" />
        <InlineField
          {...field("allocation_loss_risk_percent")}
          label={tm("allocationLossRisk")}
          type="number"
          validate={(v) => (typeof v === "string" && v !== "" && (Number(v.replace(",", ".")) < 0 || Number(v.replace(",", ".")) > 100) ? tm("invalidPercent") : null)}
        />
        <InlineField {...field("managed_from")} label={tm("managedFrom")} type="date" />
        <InlineField {...field("managed_to")} label={tm("managedTo")} type="date" />
        <InlineField {...field("garden_notes")} label={tm("gardenNotes")} type="textarea" className="flex flex-col gap-1 sm:col-span-2 lg:col-span-3" />
        <InlineField {...field("renovation_notes")} label={tm("renovationNotes")} type="textarea" className="flex flex-col gap-1 sm:col-span-2 lg:col-span-3" />
        <InlineField {...field("notes")} label={tm("notes")} type="textarea" className="flex flex-col gap-1 sm:col-span-2 lg:col-span-3" />
      </div>
      <div className="mt-3">
        <EntryHints findings={findings} testId="property-master-hints" />
      </div>
    </EditableSection>
  );
}
