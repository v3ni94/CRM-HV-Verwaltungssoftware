"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import type { Kind } from "./types";

type Option = { id: string; label: string };

/** Übergabeprotokoll anlegen (M30): kind plus optional property and unit; the address is
 *  prefilled on the server and stays editable in the protocol. */
export function HandoverCreate({ properties }: { properties: Option[] }) {
  const t = useTranslations("Handover.create");
  const router = useRouter();
  const [kind, setKind] = useState<Kind>("rental");
  const [propertyId, setPropertyId] = useState("");
  const [units, setUnits] = useState<Option[]>([]);
  const [unitId, setUnitId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setUnitId("");
    setUnits([]);
    if (!propertyId) return;
    let active = true;
    bff<{ id: string; number: string; label: string | null }[]>(
      `/api/bff/properties/${propertyId}/units`,
    ).then((res) => {
      if (active && res.ok)
        setUnits(
          res.data.map((u) => ({
            id: u.id,
            label: u.label ? `${u.number} (${u.label})` : u.number,
          })),
        );
    });
    return () => {
      active = false;
    };
  }, [propertyId]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = { kind };
    if (unitId) body.unit_id = unitId;
    const res = await bff<{ id: string }>("/api/bff/handover/protocols", {
      method: "POST",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (res.ok) router.push(`/makler/uebergabe/${res.data.id}`);
    else setError(res.message);
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-4"
      data-testid="handover-create"
    >
      <fieldset className="flex flex-wrap gap-4">
        <legend className={ui.label}>{t("kind")}</legend>
        {(["rental", "sale", "general"] as Kind[]).map((k) => (
          <label key={k} className="flex items-center gap-1.5 text-sm">
            <input
              type="radio"
              name="kind"
              checked={kind === k}
              onChange={() => setKind(k)}
            />
            {t(`kinds.${k}`)}
          </label>
        ))}
      </fieldset>
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <label htmlFor="property" className={ui.label}>
            {t("property")}
          </label>
          <select
            id="property"
            className={ui.input}
            value={propertyId}
            onChange={(e) => setPropertyId(e.target.value)}
          >
            <option value="">{t("noProperty")}</option>
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
          <select
            id="unit"
            className={ui.input}
            value={unitId}
            onChange={(e) => setUnitId(e.target.value)}
            disabled={!propertyId}
          >
            <option value="">–</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <p className={ui.help}>{t("help")}</p>
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
