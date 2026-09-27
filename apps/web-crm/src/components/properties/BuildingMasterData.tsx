"use client";
/** Stammdaten des Gebäudes, an Ort und Stelle editierbar (AP8, ADR 0012): PATCH /buildings/{id}
 *  mit If-Match aus `version`. Der Energieausweis hat seine eigene Komponente. */
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { EditableSection } from "@/components/common/EditableSection";
import { InlineField, type InlineValue } from "@/components/common/InlineField";
import { useAutosave } from "@/components/common/useAutosave";

import { area, nonNegative } from "./PropertyMasterData";

export type BuildingMaster = {
  id: string;
  property_id: string;
  version: number;
  name: string;
  street?: string | null;
  house_number?: string | null;
  address_addition?: string | null;
  construction_year?: number | null;
  renovation_level?: string | null;
  construction_type_code?: string | null;
  building_type_code?: string | null;
  floors?: number | null;
  windows?: number | null;
  total_area_sqm?: string | null;
  living_commercial_area_sqm?: string | null;
  heated_area_sqm?: string | null;
  window_area_sqm?: string | null;
  hallway_area_sqm?: string | null;
  gross_floor_area_sqm?: string | null;
  built_area_sqm?: string | null;
  sealed_area_sqm?: string | null;
  roof_area_sqm?: string | null;
  elevator?: boolean;
  cellar_rooms?: number | null;
  heritage_protection?: boolean;
  heritage_notes?: string | null;
  notes?: string | null;
};

export function BuildingMasterData({ building, canEdit }: { building: BuildingMaster; canEdit: boolean }) {
  const t = useTranslations("Buildings.masterData");
  const router = useRouter();
  const autosave = useAutosave<BuildingMaster>({ path: `buildings/${building.id}`, version: building.version, onSaved: () => router.refresh() });
  const current = { ...building, ...(autosave.data ?? {}) };
  const field = (name: keyof BuildingMaster) => ({ name, value: current[name] as InlineValue, onSave: autosave.save, state: autosave.fieldState(name) });
  const areaCheck = nonNegative(t("invalidArea"));
  const areaField = (name: keyof BuildingMaster, label: string) => (
    <InlineField {...field(name)} label={label} type="number" format={area} validate={areaCheck} />
  );
  const wide = "flex flex-col gap-1 sm:col-span-2 lg:col-span-3";
  return (
    <EditableSection
      title={t("title")}
      description={t("description")}
      canEdit={canEdit}
      status={autosave.status}
      conflict={autosave.conflict}
      onEditingChange={(editing) => {
        if (!editing) void autosave.flush();
      }}
      testId="building-master-data"
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <InlineField {...field("name")} label={t("name")} required maxLength={200} />
        <InlineField {...field("street")} label={t("street")} />
        <InlineField {...field("house_number")} label={t("houseNumber")} />
        <InlineField {...field("address_addition")} label={t("addressAddition")} maxLength={200} />
        <InlineField
          {...field("construction_year")}
          label={t("constructionYear")}
          type="number"
          numberAs="number"
          validate={(v) => (typeof v === "number" && !/^\d{4}$/.test(String(v)) ? t("invalidYear") : null)}
        />
        <InlineField {...field("renovation_level")} label={t("renovationLevel")} />
        <InlineField {...field("construction_type_code")} label={t("constructionTypeCode")} />
        <InlineField {...field("building_type_code")} label={t("buildingTypeCode")} />
        <InlineField {...field("floors")} label={t("floors")} type="number" numberAs="number" />
        <InlineField {...field("windows")} label={t("windows")} type="number" numberAs="number" />
        <InlineField {...field("cellar_rooms")} label={t("cellarRooms")} type="number" numberAs="number" />
        {areaField("total_area_sqm", t("totalArea"))}
        {areaField("living_commercial_area_sqm", t("livingCommercialArea"))}
        {areaField("heated_area_sqm", t("heatedArea"))}
        {areaField("window_area_sqm", t("windowArea"))}
        {areaField("hallway_area_sqm", t("hallwayArea"))}
        {areaField("gross_floor_area_sqm", t("grossFloorArea"))}
        {areaField("built_area_sqm", t("builtArea"))}
        {areaField("sealed_area_sqm", t("sealedArea"))}
        {areaField("roof_area_sqm", t("roofArea"))}
        <InlineField {...field("elevator")} label={t("elevator")} type="boolean" />
        <InlineField {...field("heritage_protection")} label={t("heritageProtection")} type="boolean" />
        <InlineField {...field("heritage_notes")} label={t("heritageNotes")} type="textarea" className={wide} />
        <InlineField {...field("notes")} label={t("notes")} type="textarea" className={wide} />
      </div>
    </EditableSection>
  );
}
