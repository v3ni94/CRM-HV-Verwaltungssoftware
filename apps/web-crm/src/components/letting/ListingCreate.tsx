"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Option = { id: string; label: string };

type Prefill = {
  title: string;
  living_area_sqm: string | null;
  rooms: string | null;
  floor: string | null;
};

type ListingForm = {
  title: string;
  description: string;
  price: string;
  additional_costs: string;
  deposit: string;
  available_from: string;
  commission_note: string;
  energy_note: string;
  living_area_sqm: string;
  rooms: string;
  floor: string;
  notes: string;
};

const EMPTY: ListingForm = {
  title: "",
  description: "",
  price: "",
  additional_costs: "",
  deposit: "",
  available_from: "",
  commission_note: "",
  energy_note: "",
  living_area_sqm: "",
  rooms: "",
  floor: "",
  notes: "",
};

/** Makler (M28-01): create a listing from a property and one of its units. Prefill loads the
 *  master data snapshot; it stays editable and is never re-derived automatically afterwards. */
export function ListingCreate({ properties }: { properties: Option[] }) {
  const t = useTranslations("Broker.create");
  const router = useRouter();
  const [propertyId, setPropertyId] = useState("");
  const [units, setUnits] = useState<Option[]>([]);
  const [unitId, setUnitId] = useState("");
  const [kind, setKind] = useState<"rental" | "sale">("rental");
  const [form, setForm] = useState<ListingForm>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    const body: Record<string, unknown> = { unit_id: unitId, kind };
    for (const [key, value] of Object.entries(form)) {
      if (value !== "") body[key] = value;
    }
    const res = await bff<{ id: string }>("/api/bff/letting/listings", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) {
      router.push(`/makler/${res.data.id}`);
    } else {
      setError(res.message);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" data-testid="listing-create">
      <div className="grid gap-3 md:grid-cols-3">
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
      </div>
      <button type="button" className={ui.button} onClick={prefill} disabled={!unitId}>
        {t("prefill")}
      </button>
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <label htmlFor="title" className={ui.label}>
            {t("listingTitle")}
          </label>
          <input id="title" className={ui.input} value={form.title} onChange={(e) => set("title", e.target.value)} />
        </div>
        <div>
          <label htmlFor="price" className={ui.label}>
            {t("price")}
          </label>
          <input id="price" className={ui.input} value={form.price} onChange={(e) => set("price", e.target.value)} />
        </div>
        <div>
          <label htmlFor="additional_costs" className={ui.label}>
            {t("additionalCosts")}
          </label>
          <input id="additional_costs" className={ui.input} value={form.additional_costs} onChange={(e) => set("additional_costs", e.target.value)} />
        </div>
        <div>
          <label htmlFor="deposit" className={ui.label}>
            {t("deposit")}
          </label>
          <input id="deposit" className={ui.input} value={form.deposit} onChange={(e) => set("deposit", e.target.value)} />
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
      <div>
        <label htmlFor="description" className={ui.label}>
          {t("description")}
        </label>
        <textarea id="description" className={ui.input} rows={4} value={form.description} onChange={(e) => set("description", e.target.value)} />
      </div>
      <div>
        <label htmlFor="notes" className={ui.label}>
          {t("notes")}
        </label>
        <textarea id="notes" className={ui.input} rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} />
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <button type="submit" className={ui.primary} disabled={busy}>
        {t("submit")}
      </button>
    </form>
  );
}
