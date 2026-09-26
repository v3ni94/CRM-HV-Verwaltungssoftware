"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { ADDRESS_RELEASES, ENERGY_STATUSES, ENERGY_TYPES, FEATURE_KEYS, OBJECT_TYPES } from "./ListingCreate";
import { ListingImages } from "./ListingImages";
import { OpenImmoExport } from "./OpenImmoExport";

export type Listing = {
  id: string;
  property_id: string;
  unit_id: string;
  kind: "rental" | "sale";
  status: "draft" | "active" | "reserved" | "inactive";
  title: string;
  description: string | null;
  object_type: string;
  address_release: string;
  price: string | null;
  additional_costs: string | null;
  heating_type: string | null;
  energy_source: string | null;
  heating_costs: string | null;
  heating_in_additional_costs: boolean;
  warm_rent: string | null;
  deposit: string | null;
  hoa_fee: string | null;
  parking_price: string | null;
  available_from: string | null;
  energy_status: string;
  energy_type: string | null;
  energy_value: string | null;
  energy_class: string | null;
  energy_year_of_installation: number | null;
  energy_valid_until: string | null;
  energy_issued_on: string | null;
  energy_building_year: number | null;
  energy_includes_hot_water: boolean;
  features: Record<string, boolean> | null;
  commission_type: string | null;
  commission_note: string | null;
  energy_note: string | null;
  living_area_sqm: string | null;
  rooms: string | null;
  floor: string | null;
  publication_status: string;
  notes: string | null;
  warnings?: string[];
};

const NEXT: Record<string, { action: string; status: Listing["status"] }[]> = {
  draft: [{ action: "activate", status: "active" }],
  active: [
    { action: "reserve", status: "reserved" },
    { action: "deactivate", status: "inactive" },
  ],
  reserved: [
    { action: "activate", status: "active" },
    { action: "deactivate", status: "inactive" },
  ],
  inactive: [{ action: "toDraft", status: "draft" }],
};

type Form = {
  title: string;
  description: string;
  object_type: string;
  address_release: string;
  price: string;
  additional_costs: string;
  heating_costs: string;
  heating_in_additional_costs: boolean;
  deposit: string;
  hoa_fee: string;
  parking_price: string;
  available_from: string;
  energy_status: string;
  energy_type: string;
  energy_value: string;
  energy_class: string;
  energy_year_of_installation: string;
  energy_valid_until: string;
  energy_issued_on: string;
  energy_building_year: string;
  energy_includes_hot_water: boolean;
  features: Record<string, boolean>;
  commission_type: string;
  commission_note: string;
  energy_note: string;
  living_area_sqm: string;
  rooms: string;
  floor: string;
  notes: string;
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
  "energy_type",
  "energy_value",
  "energy_class",
  "energy_year_of_installation",
  "energy_valid_until",
  "energy_issued_on",
  "energy_building_year",
  "commission_type",
  "commission_note",
  "energy_note",
  "living_area_sqm",
  "rooms",
  "floor",
  "notes",
] as const;

function toForm(listing: Listing): Form {
  return {
    title: listing.title,
    description: listing.description ?? "",
    object_type: listing.object_type,
    address_release: listing.address_release,
    price: listing.price ?? "",
    additional_costs: listing.additional_costs ?? "",
    heating_costs: listing.heating_costs ?? "",
    heating_in_additional_costs: listing.heating_in_additional_costs,
    deposit: listing.deposit ?? "",
    hoa_fee: listing.hoa_fee ?? "",
    parking_price: listing.parking_price ?? "",
    available_from: listing.available_from ?? "",
    energy_status: listing.energy_status,
    energy_type: listing.energy_type ?? "",
    energy_value: listing.energy_value ?? "",
    energy_class: listing.energy_class ?? "",
    energy_year_of_installation: listing.energy_year_of_installation != null ? String(listing.energy_year_of_installation) : "",
    energy_valid_until: listing.energy_valid_until ?? "",
    energy_issued_on: listing.energy_issued_on ?? "",
    energy_building_year: listing.energy_building_year != null ? String(listing.energy_building_year) : "",
    energy_includes_hot_water: listing.energy_includes_hot_water,
    features: { ...Object.fromEntries(FEATURE_KEYS.map((k) => [k, false])), ...(listing.features ?? {}) },
    commission_type: listing.commission_type ?? "",
    commission_note: listing.commission_note ?? "",
    energy_note: listing.energy_note ?? "",
    living_area_sqm: listing.living_area_sqm ?? "",
    rooms: listing.rooms ?? "",
    floor: listing.floor ?? "",
    notes: listing.notes ?? "",
  };
}

/** Makler (M28-01): edit a listing, change its status, or delete it while still a draft.
 *  Fields follow the FLOW data contract (docs/rules/M28-01.md, Ergänzung 24.09.2026). */
export function ListingDetail({ listing }: { listing: Listing }) {
  const t = useTranslations("Broker");
  const tCreate = useTranslations("Broker.create");
  const router = useRouter();
  const [form, setForm] = useState<Form>(toForm(listing));
  const [status, setStatus] = useState(listing.status);
  const [publicationStatus] = useState(listing.publication_status);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>(listing.warnings ?? []);

  function set<K extends keyof Form>(key: K, value: Form[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function setFeature(key: string, value: boolean) {
    setForm((f) => ({ ...f, features: { ...f.features, [key]: value } }));
  }

  const warmRentPreview = useMemo(() => {
    if (listing.kind !== "rental" || form.price === "") return null;
    const price = Number(form.price);
    const additional = form.additional_costs === "" ? 0 : Number(form.additional_costs);
    const heating = form.heating_costs === "" ? 0 : Number(form.heating_costs);
    if (Number.isNaN(price) || Number.isNaN(additional) || Number.isNaN(heating)) return null;
    const total = form.heating_in_additional_costs ? price + additional : price + additional + heating;
    return total.toFixed(2).replace(".", ",");
  }, [listing.kind, form.price, form.additional_costs, form.heating_costs, form.heating_in_additional_costs]);

  const energyDisabled = form.energy_status === "nicht_erforderlich";

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = {
      object_type: form.object_type,
      address_release: form.address_release,
      energy_status: form.energy_status,
      heating_in_additional_costs: form.heating_in_additional_costs,
      energy_includes_hot_water: form.energy_includes_hot_water,
      features: Object.fromEntries(FEATURE_KEYS.filter((k) => form.features[k]).map((k) => [k, true])),
    };
    for (const key of STRING_FIELDS) {
      const value = form[key];
      body[key] = value === "" ? null : value;
    }
    const res = await bff<Listing>(`/api/bff/letting/listings/${listing.id}`, { method: "PATCH", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
    } else {
      setWarnings(res.data.warnings ?? []);
      router.refresh();
    }
  }

  async function changeStatus(next: Listing["status"]) {
    setBusy(true);
    setError(null);
    const res = await bff<Listing>(`/api/bff/letting/listings/${listing.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: next }),
    });
    setBusy(false);
    if (res.ok) {
      setStatus(res.data.status);
      setWarnings(res.data.warnings ?? []);
      router.refresh();
    } else {
      setError(res.message);
    }
  }

  async function remove() {
    if (!window.confirm(t("detail.confirmDelete"))) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/letting/listings/${listing.id}`, { method: "DELETE" });
    setBusy(false);
    if (res.ok) router.push("/makler");
    else setError(res.message);
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className={ui.badgeGold}>{status}</span>
        <span className={ui.badge} data-testid="listing-publication-status">
          {publicationStatus === "not_published" ? t("notPublished") : publicationStatus}
        </span>
        {NEXT[status]?.map((n) => (
          <button key={n.action} type="button" className={ui.button} disabled={busy} onClick={() => changeStatus(n.status)}>
            {t(`detail.${n.action}`)}
          </button>
        ))}
        {status === "draft" ? (
          <button type="button" className={ui.danger} disabled={busy} onClick={remove}>
            {t("detail.delete")}
          </button>
        ) : null}
        <Link href={`/objekte/${listing.property_id}`} className="ml-auto text-sm underline">
          {t("detail.back")}
        </Link>
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
      <form onSubmit={save} className="flex flex-col gap-4" data-testid="listing-edit">
        <div className={ui.card}>
          <h2 className={ui.h2}>{tCreate("sectionObject")}</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-1 md:grid-cols-2">
            <div>
              <label htmlFor="object_type" className={ui.label}>
                {tCreate("objectType")}
              </label>
              <select id="object_type" className={ui.input} value={form.object_type} onChange={(e) => set("object_type", e.target.value)}>
                {OBJECT_TYPES.map((v) => (
                  <option key={v} value={v}>
                    {tCreate(`objectTypeValues.${v}`)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="title" className={ui.label}>
                {tCreate("listingTitle")}
              </label>
              <input id="title" className={ui.input} value={form.title} onChange={(e) => set("title", e.target.value)} />
            </div>
            <div>
              <label htmlFor="available_from" className={ui.label}>
                {tCreate("availableFrom")}
              </label>
              <input id="available_from" type="date" className={ui.input} value={form.available_from} onChange={(e) => set("available_from", e.target.value)} />
            </div>
            <div>
              <label htmlFor="living_area_sqm" className={ui.label}>
                {tCreate("livingArea")}
              </label>
              <input id="living_area_sqm" className={ui.input} value={form.living_area_sqm} onChange={(e) => set("living_area_sqm", e.target.value)} />
            </div>
            <div>
              <label htmlFor="rooms" className={ui.label}>
                {tCreate("rooms")}
              </label>
              <input id="rooms" className={ui.input} value={form.rooms} onChange={(e) => set("rooms", e.target.value)} />
            </div>
            <div>
              <label htmlFor="floor" className={ui.label}>
                {tCreate("floor")}
              </label>
              <input id="floor" className={ui.input} value={form.floor} onChange={(e) => set("floor", e.target.value)} />
            </div>
          </div>
          <div className="mt-3">
            <label htmlFor="description" className={ui.label}>
              {tCreate("description")}
            </label>
            <textarea id="description" className={ui.input} rows={4} value={form.description} onChange={(e) => set("description", e.target.value)} />
          </div>
        </div>

        <div className={ui.card}>
          <h2 className={ui.h2}>{tCreate("sectionAddress")}</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-1 md:grid-cols-2">
            <div>
              <label htmlFor="address_release" className={ui.label}>
                {tCreate("addressRelease")}
              </label>
              <select id="address_release" className={ui.input} value={form.address_release} onChange={(e) => set("address_release", e.target.value)}>
                {ADDRESS_RELEASES.map((v) => (
                  <option key={v} value={v}>
                    {tCreate(`addressReleaseValues.${v}`)}
                  </option>
                ))}
              </select>
              <p className={ui.help}>{tCreate("addressReleaseHelp")}</p>
            </div>
          </div>
        </div>

        <div className={ui.card}>
          <h2 className={ui.h2}>{tCreate("sectionPrices")}</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-1 md:grid-cols-2">
            <div>
              <label htmlFor="price" className={ui.label}>
                {listing.kind === "rental" ? tCreate("coldRent") : tCreate("purchasePrice")}
              </label>
              <input id="price" className={ui.input} value={form.price} onChange={(e) => set("price", e.target.value)} />
            </div>
            {listing.kind === "rental" ? (
              <>
                <div>
                  <label htmlFor="additional_costs" className={ui.label}>
                    {tCreate("additionalCosts")}
                  </label>
                  <input id="additional_costs" className={ui.input} value={form.additional_costs} onChange={(e) => set("additional_costs", e.target.value)} />
                </div>
                <div>
                  <label htmlFor="heating_costs" className={ui.label}>
                    {tCreate("heatingCosts")}
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
                    {tCreate("heatingInAdditionalCosts")}
                  </label>
                </div>
                <div>
                  <label htmlFor="deposit" className={ui.label}>
                    {tCreate("deposit")}
                  </label>
                  <input id="deposit" className={ui.input} value={form.deposit} onChange={(e) => set("deposit", e.target.value)} />
                </div>
                <div>
                  <label htmlFor="warm_rent" className={ui.label}>
                    {tCreate("warmRent")}
                  </label>
                  <input id="warm_rent" className={ui.input} value={listing.warm_rent ?? warmRentPreview ?? ""} readOnly disabled />
                  <p className={ui.help}>{tCreate("warmRentHelp")}</p>
                </div>
              </>
            ) : (
              <>
                <div>
                  <label htmlFor="hoa_fee" className={ui.label}>
                    {tCreate("hoaFee")}
                  </label>
                  <input id="hoa_fee" className={ui.input} value={form.hoa_fee} onChange={(e) => set("hoa_fee", e.target.value)} />
                </div>
                <div>
                  <label htmlFor="parking_price" className={ui.label}>
                    {tCreate("parkingPrice")}
                  </label>
                  <input id="parking_price" className={ui.input} value={form.parking_price} onChange={(e) => set("parking_price", e.target.value)} />
                </div>
              </>
            )}
          </div>
        </div>

        <div className={ui.card}>
          <h2 className={ui.h2}>{tCreate("sectionEnergy")}</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-1 md:grid-cols-2">
            <div>
              <label htmlFor="energy_status" className={ui.label}>
                {tCreate("energyStatus")}
              </label>
              <select id="energy_status" className={ui.input} value={form.energy_status} onChange={(e) => set("energy_status", e.target.value)}>
                {ENERGY_STATUSES.map((v) => (
                  <option key={v} value={v}>
                    {tCreate(`energyStatusValues.${v}`)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="energy_type" className={ui.label}>
                {tCreate("energyType")}
              </label>
              <select id="energy_type" className={ui.input} value={form.energy_type} onChange={(e) => set("energy_type", e.target.value)} disabled={energyDisabled}>
                <option value="">–</option>
                {ENERGY_TYPES.map((v) => (
                  <option key={v} value={v}>
                    {tCreate(`energyTypeValues.${v}`)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="energy_value" className={ui.label}>
                {tCreate("energyValue")}
              </label>
              <input id="energy_value" className={ui.input} value={form.energy_value} onChange={(e) => set("energy_value", e.target.value)} disabled={energyDisabled} />
            </div>
            <div>
              <label htmlFor="energy_class" className={ui.label}>
                {tCreate("energyClass")}
              </label>
              <input id="energy_class" className={ui.input} value={form.energy_class} onChange={(e) => set("energy_class", e.target.value)} disabled={energyDisabled} />
            </div>
            <div>
              <label htmlFor="energy_year_of_installation" className={ui.label}>
                {tCreate("energyYearOfInstallation")}
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
                {tCreate("energyValidUntil")}
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
            <div>
              <label htmlFor="energy_issued_on" className={ui.label}>
                {tCreate("energyIssuedOn")}
              </label>
              <input
                id="energy_issued_on"
                type="date"
                className={ui.input}
                value={form.energy_issued_on}
                onChange={(e) => set("energy_issued_on", e.target.value)}
                disabled={energyDisabled}
              />
            </div>
            <div>
              <label htmlFor="energy_building_year" className={ui.label}>
                {tCreate("energyBuildingYear")}
              </label>
              <input
                id="energy_building_year"
                className={ui.input}
                value={form.energy_building_year}
                onChange={(e) => set("energy_building_year", e.target.value)}
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
                {tCreate("energyIncludesHotWater")}
              </label>
            </div>
          </div>
        </div>

        <div className={ui.card}>
          <h2 className={ui.h2}>{tCreate("sectionFeatures")}</h2>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 md:grid-cols-3">
            {FEATURE_KEYS.map((key) => (
              <label key={key} htmlFor={`feature_${key}`} className="flex items-center gap-1.5 text-sm">
                <input
                  id={`feature_${key}`}
                  type="checkbox"
                  checked={form.features[key] ?? false}
                  onChange={(e) => setFeature(key, e.target.checked)}
                />
                {tCreate(`featureValues.${key}`)}
              </label>
            ))}
          </div>
        </div>

        <div className={ui.card}>
          <h2 className={ui.h2}>{tCreate("sectionMarketing")}</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-1 md:grid-cols-2">
            <div>
              <label htmlFor="commission_type" className={ui.label}>
                {tCreate("commissionType")}
              </label>
              <input id="commission_type" className={ui.input} value={form.commission_type} onChange={(e) => set("commission_type", e.target.value)} />
            </div>
            <div>
              <label htmlFor="commission_note" className={ui.label}>
                {tCreate("commissionNote")}
              </label>
              <input id="commission_note" className={ui.input} value={form.commission_note} onChange={(e) => set("commission_note", e.target.value)} />
            </div>
            <div>
              <label htmlFor="energy_note" className={ui.label}>
                {tCreate("energyNote")}
              </label>
              <input id="energy_note" className={ui.input} value={form.energy_note} onChange={(e) => set("energy_note", e.target.value)} />
            </div>
          </div>
          <div className="mt-3">
            <label htmlFor="notes" className={ui.label}>
              {tCreate("notes")}
            </label>
            <textarea id="notes" className={ui.input} rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} />
          </div>
          <p className={`${ui.notice} mt-3`}>{t("flowfactNotice")}</p>
        </div>

        <button type="submit" className={ui.primary} disabled={busy}>
          {t("detail.save")}
        </button>
      </form>
      <ListingImages listingId={listing.id} />
      <OpenImmoExport listingId={listing.id} />
    </div>
  );
}
