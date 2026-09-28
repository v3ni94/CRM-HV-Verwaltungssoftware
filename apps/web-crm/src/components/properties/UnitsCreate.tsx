"use client";
/** Einheit anlegen (C1, Handbuch Stammdaten): Formular auf der Objekt- und Gebäudeseite über
 *  POST /properties/{id}/units. Pflicht sind Gebäude, Nummer und Art; die Nummer muss im Objekt
 *  eindeutig sein (Hinweis vor dem Speichern, die API antwortet sonst mit 409). Flächen, Zimmer
 *  und alle weiteren Angaben werden danach auf der Einheitenseite gepflegt; Schlüsselwerte im
 *  Abschnitt Umlageschlüssel. */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export const UNIT_TYPES = ["apartment", "commercial", "office", "parking", "garage", "storage", "garden", "other"] as const;

const DECIMAL = /^[0-9]{1,10}([.,][0-9]{1,8})?$/;
const ROOMS = /^[0-9]{1,3}([.,][0-9])?$/;

/** "65,5" -> "65.5" for the API (no float, string stays a string). */
export function decimalForApi(value: string): string {
  return value.trim().replace(",", ".");
}

type Draft = {
  building_id: string;
  number: string;
  label: string;
  unit_type: string;
  location: string;
  floor: string;
  living_area_sqm: string;
  total_area_sqm: string;
  rooms: string;
};

export function UnitsCreate({
  propertyId,
  buildings,
  existingNumbers,
  defaultBuildingId,
  canCreate,
}: {
  propertyId: string;
  buildings: { id: string; name: string }[];
  existingNumbers: string[];
  defaultBuildingId?: string;
  canCreate: boolean;
}) {
  const t = useTranslations("Units.create");
  const tp = useTranslations("Properties");
  const router = useRouter();
  const empty = (): Draft => ({
    building_id: defaultBuildingId ?? buildings[0]?.id ?? "",
    number: "",
    label: "",
    unit_type: "apartment",
    location: "",
    floor: "",
    living_area_sqm: "",
    total_area_sqm: "",
    rooms: "",
  });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<Draft>(empty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ id: string; number: string } | null>(null);
  if (!canCreate) return null;
  const set = (k: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF((p) => ({ ...p, [k]: e.target.value }));
  const number = f.number.trim();
  const taken = new Set(existingNumbers.map((n) => n.trim().toLowerCase()));
  const duplicate = number !== "" && taken.has(number.toLowerCase());
  const areasValid = (["living_area_sqm", "total_area_sqm"] as const).every((k) => f[k].trim() === "" || DECIMAL.test(f[k].trim()));
  const roomsValid = f.rooms.trim() === "" || ROOMS.test(f.rooms.trim());
  const valid = f.building_id !== "" && number !== "" && !duplicate && areasValid && roomsValid;
  const hint = duplicate ? t("duplicateNumber", { number }) : !areasValid ? t("invalidArea") : !roomsValid ? t("invalidRooms") : null;

  const reset = () => {
    setF(empty());
    setOpen(false);
    setError(null);
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = { building_id: f.building_id, number, unit_type: f.unit_type };
    for (const k of ["label", "location", "floor"] as const) {
      if (f[k].trim()) body[k] = f[k].trim();
    }
    for (const k of ["living_area_sqm", "total_area_sqm", "rooms"] as const) {
      if (f[k].trim()) body[k] = decimalForApi(f[k]);
    }
    const res = await bff<{ id: string; number: string }>(`/api/bff/properties/${propertyId}/units`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setCreated({ id: res.data.id, number: res.data.number });
    reset();
    router.refresh();
  };

  const field = (k: Exclude<keyof Draft, "building_id" | "unit_type">, extra?: Partial<React.InputHTMLAttributes<HTMLInputElement>>) => (
    <label className="flex flex-col gap-1">
      <span className={ui.label}>{t(`fields.${k}`)}</span>
      <input className={ui.input} value={f[k]} onChange={set(k)} {...extra} />
    </label>
  );

  return (
    <div className="flex flex-col gap-2" data-testid="unit-create">
      {created ? (
        <p role="status" className={ui.success}>
          {t("created", { number: created.number })}{" "}
          <Link href={`/vermietung/einheit/${created.id}`} className="underline">
            {t("open")}
          </Link>
        </p>
      ) : null}
      {!open ? (
        <div>
          <button type="button" className={ui.buttonSm} onClick={() => setOpen(true)}>
            {t("title")}
          </button>
        </div>
      ) : buildings.length === 0 ? (
        <p className={ui.notice}>{t("noBuilding")}</p>
      ) : (
        <div role="dialog" aria-modal="false" aria-labelledby="unit-create-title" className={ui.card}>
          <h3 id="unit-create-title" className="font-medium">
            {t("title")}
          </h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("fields.building_id")}</span>
              <select className={ui.input} value={f.building_id} onChange={set("building_id")}>
                {buildings.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </label>
            {field("number")}
            {field("label")}
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("fields.unit_type")}</span>
              <select className={ui.input} value={f.unit_type} onChange={set("unit_type")}>
                {UNIT_TYPES.map((u) => (
                  <option key={u} value={u}>
                    {tp(`unitTypes.${u}`)}
                  </option>
                ))}
              </select>
            </label>
            {field("location")}
            {field("floor")}
            {field("living_area_sqm", { inputMode: "decimal" })}
            {field("total_area_sqm", { inputMode: "decimal" })}
            {field("rooms", { inputMode: "decimal" })}
          </div>
          <p className="mt-2 text-xs text-muted">{t("hint")}</p>
          {hint ? (
            <p role="status" className={`${ui.warning} mt-2`}>
              {hint}
            </p>
          ) : null}
          <div className={`${ui.formActions} mt-3`}>
            <button type="button" className={ui.primary} disabled={busy || !valid} onClick={submit}>
              {t("button")}
            </button>
            <button type="button" className={ui.button} disabled={busy} onClick={reset}>
              {t("cancel")}
            </button>
          </div>
          {error ? (
            <p role="alert" className={`${ui.alert} mt-2`}>
              {error}
            </p>
          ) : null}
        </div>
      )}
    </div>
  );
}
