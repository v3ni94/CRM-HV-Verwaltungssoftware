"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Row = { row_id: string; title: string | null; ort: string | null; strasse: string | null; status: string; is_duplicate: boolean; structure_errors: string[] };
type Option = { id: string; label: string };
type Preview = { run_id: string; filename: string; row_count: number; rows: Row[] };

/** OpenImmo Import (GAF-17): Vorschau der Datei, Übernahme je Zeile nach Auswahl von Objekt und Einheit
 *  (Auswahllisten). Die Vorschau legt nichts an. */
export function OpenImmoImport({ canApply }: { canApply: boolean }) {
  const t = useTranslations("Af20.openimmo");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [propertyId, setPropertyId] = useState("");
  const [unitId, setUnitId] = useState("");
  const [properties, setProperties] = useState<Option[]>([]);
  const [units, setUnits] = useState<Option[]>([]);
  const [applied, setApplied] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!canApply) return;
    let active = true;
    void bff<{ items?: { id: string; number?: string; name?: string }[] } | { id: string; number?: string; name?: string }[]>("/api/bff/properties?page_size=200").then((res) => {
      if (!active || !res.ok) return;
      const rows = Array.isArray(res.data) ? res.data : (res.data.items ?? []);
      setProperties(rows.map((p) => ({ id: p.id, label: [p.number, p.name].filter(Boolean).join(" ") || p.id })));
    });
    return () => {
      active = false;
    };
  }, [canApply]);
  useEffect(() => {
    setUnitId("");
    setUnits([]);
    if (!propertyId) return;
    let active = true;
    void bff<{ id: string; number: string; label: string | null }[]>(`/api/bff/properties/${propertyId}/units`).then((res) => {
      if (active && res.ok) setUnits(res.data.map((u) => ({ id: u.id, label: u.label ? `${u.number} (${u.label})` : u.number })));
    });
    return () => {
      active = false;
    };
  }, [propertyId]);
  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.set("file", file);
    const res = await bff<Preview>("/api/bff/letting/openimmo-import/preview", { method: "POST", body: form });
    setBusy(false);
    if (res.ok) setPreview(res.data);
    else setError(res.message);
  };
  const apply = async (row: Row) => {
    if (!preview) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/letting/openimmo-import/${preview.run_id}/rows/${row.row_id}/apply`, {
      method: "POST",
      body: JSON.stringify({ property_id: propertyId.trim(), unit_id: unitId.trim() }),
    });
    setBusy(false);
    if (res.ok) setApplied((prev) => ({ ...prev, [row.row_id]: true }));
    else setError(res.message);
  };
  return (
    <section className={ui.card} data-testid="openimmo-import">
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <p className="text-xs text-muted">{t("intro")}</p>
      <label className="mt-2 flex flex-col gap-1">
        <span className={ui.label}>{t("file")}</span>
        <input type="file" accept=".xml,.zip" disabled={busy} onChange={(e) => void upload(e.target.files?.[0])} />
      </label>
      {preview ? (
        <div className="mt-2 flex flex-col gap-2">
          <p className="text-xs text-muted">{t("count", { file: preview.filename, count: preview.row_count })}</p>
          {canApply ? (
            <div className="flex flex-wrap gap-2">
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("property")}</span>
                <select className={ui.input} value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
                  <option value="">{t("choose")}</option>
                  {properties.map((p) => (
                    <option key={p.id} value={p.id}>{p.label}</option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("unit")}</span>
                <select className={ui.input} value={unitId} disabled={!propertyId} onChange={(e) => setUnitId(e.target.value)}>
                  <option value="">{t("choose")}</option>
                  {units.map((u) => (
                    <option key={u.id} value={u.id}>{u.label}</option>
                  ))}
                </select>
              </label>
            </div>
          ) : null}
          <ul className="flex flex-col gap-1 text-sm">
            {preview.rows.map((r) => (
              <li key={r.row_id} className="flex flex-wrap items-center gap-2">
                <span>{r.title ?? t("untitled")}</span>
                <span className="text-xs text-muted">{[r.strasse, r.ort].filter(Boolean).join(", ")}</span>
                {r.is_duplicate ? <span className={ui.badgeWarning}>{t("duplicate")}</span> : null}
                {r.structure_errors.length ? <span className={ui.badgeWarning}>{t("errors", { count: r.structure_errors.length })}</span> : null}
                {applied[r.row_id] ? (
                  <span className={ui.badge}>{t("applied")}</span>
                ) : canApply ? (
                  <button type="button" className={ui.buttonSm} disabled={busy || r.is_duplicate || !propertyId.trim() || !unitId.trim()} onClick={() => void apply(r)}>
                    {t("apply")}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
