"use client";
/** Stammdaten der Einheit, an Ort und Stelle editierbar (AP8, ADR 0012): PATCH /units/{id} mit
 *  If-Match aus `version`. Provision und Kaution sind Stammwerte der Einheit, keine Buchungen;
 *  Umlagewerte, Eigentümer und Mieter bleiben in ihren eigenen Abschnitten. */
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { EditableSection } from "@/components/common/EditableSection";
import { InlineField, type InlineOption, type InlineValue } from "@/components/common/InlineField";
import { useAutosave } from "@/components/common/useAutosave";
import { formatEur } from "@/lib/format";
import { formatQty } from "@/lib/units";

import { area, nonNegative } from "./PropertyMasterData";

export type UnitMaster = {
  id: string;
  property_id: string;
  building_id: string;
  version: number;
  number: string;
  label?: string | null;
  location?: string | null;
  unit_type: string;
  internal_name?: string | null;
  rooms?: string | null;
  bedrooms?: number | null;
  bathrooms?: number | null;
  total_area_sqm?: string | null;
  living_area_sqm?: string | null;
  floor?: string | null;
  last_modernization_year?: number | null;
  is_fictional?: boolean;
  cellar_number?: string | null;
  features?: string | null;
  street?: string | null;
  house_number?: string | null;
  postal_code?: string | null;
  city?: string | null;
  sub_community_id?: string | null;
  commission?: string | null;
  commission_note?: string | null;
  deposit_amount?: string | null;
  vacancy_vat_option?: string | null;
};

const UNIT_TYPES = ["apartment", "commercial", "office", "parking", "garage", "storage", "garden", "other"];
const VAT_OPTIONS = ["none", "commercial_no_vat", "commercial_full_vat", "commercial_reduced_vat"];

export function UnitMasterData({
  unit,
  canEdit,
  subCommunities = [],
}: {
  unit: UnitMaster;
  canEdit: boolean;
  subCommunities?: { id: string; code: string; name: string }[];
}) {
  const t = useTranslations("Units");
  const tm = useTranslations("Units.masterData");
  const tp = useTranslations("Properties");
  const router = useRouter();
  const autosave = useAutosave<UnitMaster>({ path: `units/${unit.id}`, version: unit.version, onSaved: () => router.refresh() });
  const current = { ...unit, ...(autosave.data ?? {}) };
  const field = (name: keyof UnitMaster) => ({ name, value: current[name] as InlineValue, onSave: autosave.save, state: autosave.fieldState(name) });
  const unitTypes: InlineOption[] = UNIT_TYPES.map((v) => ({ value: v, label: tp(`unitTypes.${v}`) }));
  const vatOptions: InlineOption[] = VAT_OPTIONS.map((v) => ({ value: v, label: t(`vatOptions.${v}`) }));
  const communities: InlineOption[] = subCommunities.map((c) => ({ value: c.id, label: `${c.code} ${c.name}` }));
  const areaCheck = nonNegative(tp("masterData.invalidArea"));
  const amountCheck = nonNegative(tm("invalidAmount"));
  const eur = (v: InlineValue) => (v == null || v === "" ? "" : formatEur(String(v)));
  const wide = "flex flex-col gap-1 sm:col-span-2 lg:col-span-3";
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
      testId="unit-master-data"
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <InlineField {...field("number")} label={t("number")} required maxLength={20} />
        <InlineField {...field("label")} label={t("label")} maxLength={50} />
        <InlineField {...field("internal_name")} label={t("internalName")} />
        <InlineField {...field("unit_type")} label={t("type")} type="select" options={unitTypes} required />
        <InlineField {...field("location")} label={t("location")} maxLength={100} />
        <InlineField {...field("floor")} label={t("floor")} />
        <InlineField {...field("living_area_sqm")} label={t("livingArea")} type="number" format={area} validate={areaCheck} />
        <InlineField {...field("total_area_sqm")} label={t("totalArea")} type="number" format={area} validate={areaCheck} />
        <InlineField {...field("rooms")} label={t("rooms")} type="number" format={(v) => (v == null || v === "" ? "" : formatQty(String(v)))} step="0.5" />
        <InlineField {...field("bedrooms")} label={t("bedrooms")} type="number" numberAs="number" />
        <InlineField {...field("bathrooms")} label={t("bathrooms")} type="number" numberAs="number" />
        <InlineField {...field("cellar_number")} label={t("cellar")} />
        <InlineField {...field("last_modernization_year")} label={t("modernization")} type="number" numberAs="number" />
        <InlineField {...field("is_fictional")} label={tm("isFictional")} type="boolean" />
        {communities.length ? <InlineField {...field("sub_community_id")} label={tm("subCommunity")} type="select" options={communities} /> : null}
        <InlineField {...field("vacancy_vat_option")} label={tm("vacancyVatOption")} type="select" options={vatOptions} />
        <InlineField {...field("commission")} label={tm("commission")} type="number" format={eur} validate={amountCheck} />
        <InlineField {...field("deposit_amount")} label={tm("depositAmount")} type="number" format={eur} validate={amountCheck} />
        <InlineField {...field("commission_note")} label={tm("commissionNote")} />
        <InlineField {...field("street")} label={tm("street")} />
        <InlineField {...field("house_number")} label={tm("houseNumber")} />
        <InlineField {...field("postal_code")} label={tm("postalCode")} />
        <InlineField {...field("city")} label={tm("city")} />
        <InlineField {...field("features")} label={t("features")} type="textarea" className={wide} />
      </div>
    </EditableSection>
  );
}
