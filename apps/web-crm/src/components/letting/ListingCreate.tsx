"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Option = { id: string; label: string };

type Prefill = {
  title: string;
  living_area_sqm: string | null;
  rooms: string | null;
  floor: string | null;
};

export const OBJECT_TYPES = ["wohnung", "haus", "gewerbe", "stellplatz", "grundstueck"] as const;
export const ADDRESS_RELEASES = ["vollstaendig", "nur_plz_ort"] as const;
export const ENERGY_STATUSES = ["liegt_vor", "nicht_erforderlich", "in_erstellung"] as const;
export const ENERGY_TYPES = ["bedarf", "verbrauch"] as const;
export const FEATURE_KEYS = [
  "balkon",
  "terrasse",
  "garten",
  "keller",
  "aufzug",
  "einbaukueche",
  "gaeste_wc",
  "barrierefrei",
  "moebliert",
  "wg_geeignet",
  "haustiere_erlaubt",
] as const;

type ListingForm = {
  title: string;
  description: string;
  price: string;
  additional_costs: string;
  heating_costs: string;
  heating_in_additional_costs: boolean;
  deposit: string;
  hoa_fee: string;
  parking_price: string;
  available_from: string;
  commission_type: string;
  commission_note: string;
  energy_note: string;
  living_area_sqm: string;
  rooms: string;
  floor: string;
  notes: string;
  object_type: string;
  address_release: string;
  energy_status: string;
  energy_type: string;
  energy_value: string;
  energy_class: string;
  energy_year_of_installation: string;
  energy_valid_until: string;
  energy_includes_hot_water: boolean;
  features: Record<string, boolean>;
};

const EMPTY: ListingForm = {
  title: "",
  description: "",
  price: "",
  additional_costs: "",
  heating_costs: "",
  heating_in_additional_costs: false,
  deposit: "",
  hoa_fee: "",
  parking_price: "",
  available_from: "",
  commission_type: "",
  commission_note: "",
  energy_note: "",
  living_area_sqm: "",
  rooms: "",
  floor: "",
  notes: "",
  object_type: "wohnung",
  address_release: "vollstaendig",
  energy_status: "in_erstellung",
  energy_type: "",
  energy_value: "",
  energy_class: "",
  energy_year_of_installation: "",
  energy_valid_until: "",
  energy_includes_hot_water: false,
  features: Object.fromEntries(FEATURE_KEYS.map((k) => [k, false])),
};

const STRING_FIELDS = [
  "title",
  "description",
  "price",
  "additional_costs",
  "heating_costs",
  "deposit",
  "hoa_fee",
  "parking_price",
  "available_from",
  "commission_type",
  "commission_note",
  "energy_note",
  "living_area_sqm",
  "rooms",
  "floor",
  "notes",
  "energy_type",
  "energy_value",
  "energy_class",
  "energy_year_of_installation",
  "energy_valid_until",
] as const;

/** Makler (M28-01): create a listing from a property and one of its units. Prefill loads the
 *  master data snapshot; it stays editable and is never re-derived automatically afterwards.
 *  Fields follow the FLOW data contract (docs/rules/M28-01.md, Ergänzung 24.09.2026). */
export function ListingCreate({ properties }: { properties: Option[] }) {
  const t = useTranslations("Broker.create");
  const tBroker = useTranslations("Broker");
  const router = useRouter();
  const [propertyId, setPropertyId] = useState("");
  const [units, setUnits] = useState<Option[]>([]);
  const [unitId, setUnitId] = useState("");
  const [kind, setKind] = useState<"rental" | "sale">("rental");
  const [form, setForm] = useState<ListingForm>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);

  useEffect(() => {
    setUnitId("");
    setUnits([]);
    if (!propertyId) return;
    let active = true;
    bff<{ id: string; number: string; label: string | null }[]>(`/api/bff/properties/${propertyId}/units`).then((res) => {
      if (active && res.ok) setUnits(res.data.map((u) => ({ id: u.id, label: u.label ? `${u.number} (${u.label})` : u.number })));
    });
    return () => {
      active = false;
    };
  }, [propertyId]);

  async function prefill() {
    if (!unitId) {
      setError(t("selectUnit"));
      return;
    }
    setError(null);
    const res = await bff<Prefill>(`/api/bff/letting/listings/prefill?unit_id=${unitId}`);
    if (res.ok) {
      setForm((f) => ({
        ...f,
        title: res.data.title,
        living_area_sqm: res.data.living_area_sqm ?? "",
        rooms: res.data.rooms ?? "",
        floor: res.data.floor ?? "",
      }));
    } else {
      setError(res.message);
    }
  }

  function set<K extends keyof ListingForm>(key: K, value: ListingForm[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function setFeature(key: string, value: boolean) {
    setForm((f) => ({ ...f, features: { ...f.features, [key]: value } }));
  }

  const warmRentPreview = useMemo(() => {
    if (kind !== "rental" || form.price === "") return null;
    const price = Number(form.price);
    const additional = form.additional_costs === "" ? 0 : Number(form.additional_costs);
    const heating = form.heating_costs === "" ? 0 : Number(form.heating_costs);
    if (Number.isNaN(price) || Number.isNaN(additional) || Number.isNaN(heating)) return null;
    const total = form.heating_in_additional_costs ? price + additional : price + additional + heating;
    return total.toFixed(2).replace(".", ",");
  }, [kind, form.price, form.additional_costs, form.heating_costs, form.heating_in_additional_costs]);

  const energyDisabled = form.energy_status === "nicht_erforderlich";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!propertyId) {
      setError(t("selectProperty"));
      return;
    }
    if (!unitId) {
      setError(t("selectUnit"));
      return;
    }
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = {
      unit_id: unitId,
      kind,
      object_type: form.object_type,
      address_release: form.address_release,
      energy_status: form.energy_status,
      heating_in_additional_costs: form.heating_in_additional_costs,
      energy_includes_hot_water: form.energy_includes_hot_water,
    };
    for (const key of STRING_FIELDS) {
      const value = form[key];
      if (value !== "") body[key] = value;
    }
    if (form.address_release === "") delete body.address_release;
    const activeFeatures = Object.fromEntries(FEATURE_KEYS.filter((k) => form.features[k]).map((k) => [k, true]));
    if (Object.keys(activeFeatures).length > 0) body.features = activeFeatures;
    const res = await bff<{ id: string; warnings?: string[] }>("/api/bff/letting/listings", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) {
      if (res.data.warnings && res.data.warnings.length > 0) {
        setWarnings(res.data.warnings);
      }
      router.push(`/makler/${res.data.id}`);
    } else {
      setError(res.message);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" data-testid="listing-create">
      <div className={ui.card}>
        <h2 className={ui.h2}>{t("sectionObject")}</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-1 md:grid-cols-2">
          <div>
            <label htmlFor="property" className={ui.label}>
              {t("property")}
            </label>
            <select id="property" className={ui.input} value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
              <option value="">–</option>
              {properties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="unit" className={ui.label}>
              {t("unit")}
            </label>
            <select id="unit" className={ui.input} value={unitId} onChange={(e) => setUnitId(e.target.value)} disabled={!propertyId}>
              <option value="">–</option>
              {units.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.label}
                </option>
              ))}
            </select>
          </div>
          <fieldset className="flex items-end gap-4">
            <legend className="sr-only">{t("kind")}</legend>
            <label className="flex items-center gap-1.5 text-sm">
              <input type="radio" name="kind" checked={kind === "rental"} onChange={() => setKind("rental")} />
              {t("kindRental")}
            </label>
            <label className="flex items-center gap-1.5 text-sm">
              <input type="radio" name="kind" checked={kind === "sale"} onChange={() => setKind("sale")} />
              {t("kindSale")}
            </label>
          </fieldset>
          <div>
            <label htmlFor="object_type" className={ui.label}>
              {t("objectType")}
            </label>
            <select id="object_type" className={ui.input} value={form.object_type} onChange={(e) => set("object_type", e.target.value)}>
              {OBJECT_TYPES.map((v) => (
                <option key={v} value={v}>
                  {t(`objectTypeValues.${v}`)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <button type="button" className={`${ui.button} mt-3`} onClick={prefill} disabled={!unitId}>
          {t("prefill")}
        </button>
        <div className="mt-3 grid gap-3 sm:grid-cols-1 md:grid-cols-2">
          <div>
            <label htmlFor="title" className={ui.label}>
              {t("listingTitle")}
            </label>
            <input id="title" className={ui.input} value={form.title} onChange={(e) => set("title", e.target.value)} />
          </div>
          <div>
            <label htmlFor="available_from" className={ui.label}>
              {t("availableFrom")}
            </label>
            <input id="available_from" type="date" className={ui.input} value={form.available_from} onChange={(e) => set("available_from", e.target.value)} />
          </div>
          <div>
            <label htmlFor="living_area_sqm" className={ui.label}>
              {t("livingArea")}
            </label>
            <input id="living_area_sqm" className={ui.input} value={form.living_area_sqm} onChange={(e) => set("living_area_sqm", e.target.value)} />
          </div>
          <div>
            <label htmlFor="rooms" className={ui.label}>
              {t("rooms")}
            </label>
            <input id="rooms" className={ui.input} value={form.rooms} onChange={(e) => set("rooms", e.target.value)} />
          </div>
          <div>
            <label htmlFor="floor" className={ui.label}>
              {t("floor")}
            </label>
            <input id="floor" className={ui.input} value={form.floor} onChange={(e) => set("floor", e.target.value)} />
          </div>
        </div>
        <div className="mt-3">
          <label htmlFor="description" className={ui.label}>
            {t("description")}
          </label>
          <textarea id="description" className={ui.input} rows={4} value={form.description} onChange={(e) => set("description", e.target.value)} />
        </div>
      </div>

      <div className={ui.card}>
        <h2 className={ui.h2}>{t("sectionAddress")}</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-1 md:grid-cols-2">
          <div>
            <label htmlFor="address_release" className={ui.label}>
              {t("addressRelease")}
            </label>
            <select id="address_release" className={ui.input} value={form.address_release} onChange={(e) => set("address_release", e.target.value)}>
              {ADDRESS_RELEASES.map((v) => (
                <option key={v} value={v}>
                  {t(`addressReleaseValues.${v}`)}
                </option>
              ))}
            </select>
            <p className={ui.help}>{t("addressReleaseHelp")}</p>
          </div>
        </div>
      </div>

      <div className={ui.card}>
        <h2 className={ui.h2}>{t("sectionPrices")}</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-1 md:grid-cols-2">
          <div>
            <label htmlFor="price" className={ui.label}>
              {kind === "rental" ? t("coldRent") : t("purchasePrice")}
            </label>
            <input id="price" className={ui.input} value={form.price} onChange={(e) => set("price", e.target.value)} />
          </div>
          {kind === "rental" ? (
            <>
              <div>
                <label htmlFor="additional_costs" className={ui.label}>
                  {t("additionalCosts")}
                </label>
                <input id="additional_costs" className={ui.input} value={form.additional_costs} onChange={(e) => set("additional_costs", e.target.value)} />
              </div>
              <div>
                <label htmlFor="heating_costs" className={ui.label}>
                  {t("heatingCosts")}
                </label>
                <input id="heating_costs" className={ui.input} value={form.heating_costs} onChange={(e) => set("heating_costs", e.target.value)} />
              </div>
              <div className="flex items-end">
                <label htmlFor="heating_in_additional_costs" className="flex items-center gap-1.5 text-sm">
                  <input
                    id="heating_in_additional_costs"
                    type="checkbox"
                    checked={form.heating_in_additional_costs}
                    onChange={(e) => set("heating_in_additional_costs", e.target.checked)}
                  />
                  {t("heatingInAdditionalCosts")}
                </label>
              </div>
              <div>
                <label htmlFor="deposit" className={ui.label}>
                  {t("deposit")}
                </label>
                <input id="deposit" className={ui.input} value={form.deposit} onChange={(e) => set("deposit", e.target.value)} />
              </div>
              <div>
                <label htmlFor="warm_rent" className={ui.label}>
                  {t("warmRent")}
                </label>
                <input id="warm_rent" className={ui.input} value={warmRentPreview ? `${warmRentPreview} EUR` : ""} readOnly disabled />
                <p className={ui.help}>{t("warmRentHelp")}</p>
              </div>
            </>
          ) : (
            <>
              <div>
                <label htmlFor="hoa_fee" className={ui.label}>
                  {t("hoaFee")}
                </label>
                <input id="hoa_fee" className={ui.input} value={form.hoa_fee} onChange={(e) => set("hoa_fee", e.target.value)} />
              </div>
              <div>
                <label htmlFor="parking_price" className={ui.label}>
                  {t("parkingPrice")}
                </label>
                <input id="parking_price" className={ui.input} value={form.parking_price} onChange={(e) => set("parking_price", e.target.value)} />
              </div>
            </>
          )}
        </div>
      </div>

      <div className={ui.card}>
        <h2 className={ui.h2}>{t("sectionEnergy")}</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-1 md:grid-cols-2">
          <div>
            <label htmlFor="energy_status" className={ui.label}>
              {t("energyStatus")}
            </label>
            <select id="energy_status" className={ui.input} value={form.energy_status} onChange={(e) => set("energy_status", e.target.value)}>
              {ENERGY_STATUSES.map((v) => (
                <option key={v} value={v}>
                  {t(`energyStatusValues.${v}`)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="energy_type" className={ui.label}>
              {t("energyType")}
            </label>
            <select id="energy_type" className={ui.input} value={form.energy_type} onChange={(e) => set("energy_type", e.target.value)} disabled={energyDisabled}>
              <option value="">–</option>
              {ENERGY_TYPES.map((v) => (
                <option key={v} value={v}>
                  {t(`energyTypeValues.${v}`)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="energy_value" className={ui.label}>
              {t("energyValue")}
            </label>
            <input id="energy_value" className={ui.input} value={form.energy_value} onChange={(e) => set("energy_value", e.target.value)} disabled={energyDisabled} />
          </div>
          <div>
            <label htmlFor="energy_class" className={ui.label}>
              {t("energyClass")}
            </label>
            <input id="energy_class" className={ui.input} value={form.energy_class} onChange={(e) => set("energy_class", e.target.value)} disabled={energyDisabled} />
          </div>
          <div>
            <label htmlFor="energy_year_of_installation" className={ui.label}>
              {t("energyYearOfInstallation")}
            </label>
            <input
              id="energy_year_of_installation"
              className={ui.input}
              value={form.energy_year_of_installation}
              onChange={(e) => set("energy_year_of_installation", e.target.value)}
              disabled={energyDisabled}
            />
          </div>
          <div>
            <label htmlFor="energy_valid_until" className={ui.label}>
              {t("energyValidUntil")}
            </label>
            <input
              id="energy_valid_until"
              type="date"
              className={ui.input}
              value={form.energy_valid_until}
              onChange={(e) => set("energy_valid_until", e.target.value)}
              disabled={energyDisabled}
            />
          </div>
          <div className="flex items-end">
            <label htmlFor="energy_includes_hot_water" className="flex items-center gap-1.5 text-sm">
              <input
                id="energy_includes_hot_water"
                type="checkbox"
                checked={form.energy_includes_hot_water}
                onChange={(e) => set("energy_includes_hot_water", e.target.checked)}
                disabled={energyDisabled}
              />
              {t("energyIncludesHotWater")}
            </label>
          </div>
        </div>
      </div>

      <div className={ui.card}>
        <h2 className={ui.h2}>{t("sectionFeatures")}</h2>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 md:grid-cols-3">
          {FEATURE_KEYS.map((key) => (
            <label key={key} htmlFor={`feature_${key}`} className="flex items-center gap-1.5 text-sm">
              <input
                id={`feature_${key}`}
                type="checkbox"
                checked={form.features[key] ?? false}
                onChange={(e) => setFeature(key, e.target.checked)}
              />
              {t(`featureValues.${key}`)}
            </label>
          ))}
        </div>
      </div>

      <div className={ui.card}>
        <h2 className={ui.h2}>{t("sectionMarketing")}</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-1 md:grid-cols-2">
          <div>
            <label htmlFor="commission_type" className={ui.label}>
              {t("commissionType")}
            </label>
            <input id="commission_type" className={ui.input} value={form.commission_type} onChange={(e) => set("commission_type", e.target.value)} />
          </div>
          <div>
            <label htmlFor="commission_note" className={ui.label}>
              {t("commissionNote")}
            </label>
            <input id="commission_note" className={ui.input} value={form.commission_note} onChange={(e) => set("commission_note", e.target.value)} />
          </div>
          <div>
            <label htmlFor="energy_note" className={ui.label}>
              {t("energyNote")}
            </label>
            <input id="energy_note" className={ui.input} value={form.energy_note} onChange={(e) => set("energy_note", e.target.value)} />
          </div>
        </div>
        <div className="mt-3">
          <label htmlFor="notes" className={ui.label}>
            {t("notes")}
          </label>
          <textarea id="notes" className={ui.input} rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} />
        </div>
        <p className={`${ui.notice} mt-3`}>{tBroker("flowfactNotice")}</p>
      </div>

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {warnings.length > 0 ? (
        <ul role="status" className={ui.notice} data-testid="listing-warnings">
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      ) : null}
      <button type="submit" className={ui.primary} disabled={busy}>
        {t("submit")}
      </button>
    </form>
  );
}
