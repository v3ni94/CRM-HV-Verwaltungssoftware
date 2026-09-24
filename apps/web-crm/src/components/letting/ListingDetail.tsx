"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type Listing = {
  id: string;
  property_id: string;
  unit_id: string;
  kind: "rental" | "sale";
  status: "draft" | "active" | "reserved" | "inactive";
  title: string;
  description: string | null;
  price: string | null;
  additional_costs: string | null;
  deposit: string | null;
  available_from: string | null;
  commission_note: string | null;
  energy_note: string | null;
  living_area_sqm: string | null;
  rooms: string | null;
  floor: string | null;
  publication_status: string;
  notes: string | null;
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

/** Makler (M28-01): edit a listing, change its status, or delete it while still a draft. */
export function ListingDetail({ listing }: { listing: Listing }) {
  const t = useTranslations("Broker");
  const router = useRouter();
  const [form, setForm] = useState({
    title: listing.title,
    description: listing.description ?? "",
    price: listing.price ?? "",
    additional_costs: listing.additional_costs ?? "",
    deposit: listing.deposit ?? "",
    available_from: listing.available_from ?? "",
    commission_note: listing.commission_note ?? "",
    energy_note: listing.energy_note ?? "",
    living_area_sqm: listing.living_area_sqm ?? "",
    rooms: listing.rooms ?? "",
    floor: listing.floor ?? "",
    notes: listing.notes ?? "",
  });
  const [status, setStatus] = useState(listing.status);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(form)) body[key] = value === "" ? null : value;
    const res = await bff<Listing>(`/api/bff/letting/listings/${listing.id}`, { method: "PATCH", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) setError(res.message);
    else router.refresh();
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
      <form onSubmit={save} className="flex flex-col gap-4" data-testid="listing-edit">
        <div className="grid gap-3 md:grid-cols-2">
          {(
            [
              ["title", "listingTitle"],
              ["price", "price"],
              ["additional_costs", "additionalCosts"],
              ["deposit", "deposit"],
              ["available_from", "availableFrom"],
              ["living_area_sqm", "livingArea"],
              ["rooms", "rooms"],
              ["floor", "floor"],
              ["commission_note", "commissionNote"],
              ["energy_note", "energyNote"],
            ] as const
          ).map(([key, label]) => (
            <div key={key}>
              <label htmlFor={key} className={ui.label}>
                {t(`create.${label}`)}
              </label>
              <input
                id={key}
                type={key === "available_from" ? "date" : "text"}
                className={ui.input}
                value={form[key]}
                onChange={(e) => set(key, e.target.value)}
              />
            </div>
          ))}
        </div>
        <div>
          <label htmlFor="description" className={ui.label}>
            {t("create.description")}
          </label>
          <textarea id="description" className={ui.input} rows={4} value={form.description} onChange={(e) => set("description", e.target.value)} />
        </div>
        <div>
          <label htmlFor="notes" className={ui.label}>
            {t("create.notes")}
          </label>
          <textarea id="notes" className={ui.input} rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} />
        </div>
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("detail.save")}
        </button>
      </form>
    </div>
  );
}
