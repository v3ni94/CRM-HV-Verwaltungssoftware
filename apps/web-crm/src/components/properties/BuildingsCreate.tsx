"use client";
/** Gebäude anlegen (C1, Handbuch Stammdaten): Formular auf der Objektseite über
 *  POST /properties/{id}/buildings. Nur die Bezeichnung ist Pflicht; Flächen, Energieausweis und
 *  weitere Angaben werden danach auf der Gebäudeseite gepflegt. ES-03 (Hausnummer im Feld
 *  Straße) ist ein Hinweis, kein Sperrgrund. */
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { EntryHints } from "@/components/common/EntryHints";
import { bff } from "@/lib/bff";
import { checkBuilding } from "@/lib/entry-standards";
import { ui } from "@/lib/ui";

const EMPTY = { name: "", street: "", house_number: "", address_addition: "", construction_year: "", floors: "" };
type Draft = typeof EMPTY;

const YEAR = /^[0-9]{4}$/;
const COUNT = /^[0-9]{1,3}$/;

export function BuildingsCreate({ propertyId, canCreate }: { propertyId: string; canCreate: boolean }) {
  const t = useTranslations("Properties.buildings.create");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<Draft>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  if (!canCreate) return null;
  const set = (k: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement>) => setF((p) => ({ ...p, [k]: e.target.value }));
  const findings = checkBuilding(f);
  const yearValid = f.construction_year.trim() === "" || YEAR.test(f.construction_year.trim());
  const floorsValid = f.floors.trim() === "" || COUNT.test(f.floors.trim());
  const valid = f.name.trim().length > 0 && yearValid && floorsValid;
  const hint = !yearValid ? t("invalidYear") : !floorsValid ? t("invalidFloors") : null;

  const reset = () => {
    setF(EMPTY);
    setOpen(false);
    setError(null);
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = { name: f.name.trim() };
    for (const k of ["street", "house_number", "address_addition"] as const) {
      if (f[k].trim()) body[k] = f[k].trim();
    }
    if (f.construction_year.trim()) body.construction_year = Number(f.construction_year.trim());
    if (f.floors.trim()) body.floors = Number(f.floors.trim());
    const res = await bff<{ id: string; name: string }>(`/api/bff/properties/${propertyId}/buildings`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setCreated(res.data.name);
    reset();
    router.refresh();
  };

  const field = (k: keyof Draft, extra?: Partial<React.InputHTMLAttributes<HTMLInputElement>>) => (
    <label className="flex flex-col gap-1">
      <span className={ui.label}>{t(`fields.${k}`)}</span>
      <input className={ui.input} value={f[k]} onChange={set(k)} {...extra} />
    </label>
  );

  return (
    <div className="flex flex-col gap-2" data-testid="building-create">
      {created ? (
        <p role="status" className={ui.success}>
          {t("created", { name: created })}
        </p>
      ) : null}
      {!open ? (
        <div>
          <button type="button" className={ui.buttonSm} onClick={() => setOpen(true)}>
            {t("title")}
          </button>
        </div>
      ) : (
        <div role="dialog" aria-modal="false" aria-labelledby="building-create-title" className={ui.card}>
          <h3 id="building-create-title" className="font-medium">
            {t("title")}
          </h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            {field("name")}
            {field("street")}
            {field("house_number")}
            {field("address_addition")}
            {field("construction_year", { inputMode: "numeric" })}
            {field("floors", { inputMode: "numeric" })}
          </div>
          <p className="mt-2 text-xs text-muted">{t("hint")}</p>
          <div className="mt-2">
            <EntryHints findings={findings} testId="building-create-hints" />
          </div>
          {hint ? <p className="mt-2 text-sm text-muted">{hint}</p> : null}
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
