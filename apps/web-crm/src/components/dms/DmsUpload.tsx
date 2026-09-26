"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type PropertyItem = { id: string; number: string; name: string };
type UnitItem = { id: string; number: string; label: string | null };
type Filing = {
  routed: boolean;
  status?: "pending" | "submitted" | "done" | "failed";
  last_error?: string | null;
};

/** Upload into the CRM with the object (and optionally the unit) it belongs to (26.09.2026).
 *  With the objektakte upload switched on, the document goes to objektakte, which files it in
 *  the Drive structure of the object (owner and tenant files) and in Paperless; otherwise the
 *  CRM's own mirrors apply. The filing state is shown right after the upload. */
export function DmsUpload() {
  const t = useTranslations("DmsSearch.upload");
  const [properties, setProperties] = useState<PropertyItem[]>([]);
  const [propertyId, setPropertyId] = useState("");
  const [units, setUnits] = useState<UnitItem[]>([]);
  const [unitId, setUnitId] = useState("");
  const [title, setTitle] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ id: string; filing: Filing | null } | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      const res = await bff<{ items: PropertyItem[] }>("/api/bff/properties?page_size=200");
      if (active && res.ok) setProperties(res.data.items);
    })();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    setUnits([]);
    setUnitId("");
    if (!propertyId) return;
    let active = true;
    void (async () => {
      const res = await bff<{ items: UnitItem[] } | UnitItem[]>(`/api/bff/properties/${propertyId}/units`);
      if (!active || !res.ok) return;
      setUnits(Array.isArray(res.data) ? res.data : res.data.items);
    })();
    return () => {
      active = false;
    };
  }, [propertyId]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file || !propertyId) {
      setError(t("errors.missing"));
      return;
    }
    setBusy(true);
    setError(null);
    setDone(null);
    const links = [{ entity_type: unitId ? "unit" : "property", entity_id: unitId || propertyId, role: "original" }];
    const body = new FormData();
    body.set("file", file);
    if (title.trim()) body.set("title", title.trim());
    body.set("links", JSON.stringify(links));
    const res = await bff<{ id: string }>("/api/bff/documents", { method: "POST", body });
    if (!res.ok) {
      setBusy(false);
      setError(res.message);
      return;
    }
    const filing = await bff<Filing>(`/api/bff/integrations/objektakte/documents/${res.data.id}/filing`);
    setBusy(false);
    setDone({ id: res.data.id, filing: filing.ok ? filing.data : null });
    setTitle("");
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="text-sm text-muted">{t("intro")}</p>
      <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => void submit(e)} data-testid="dms-upload-form">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{t("file")}</span>
          <input ref={fileRef} type="file" className={ui.input} aria-label={t("file")} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{t("property")}</span>
          <select className={`${ui.input} w-auto`} value={propertyId} onChange={(e) => setPropertyId(e.target.value)} aria-label={t("property")}>
            <option value="">{t("choose")}</option>
            {properties.map((p) => (
              <option key={p.id} value={p.id}>
                {p.number} {p.name}
              </option>
            ))}
          </select>
        </label>
        {units.length > 0 ? (
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted">{t("unit")}</span>
            <select className={`${ui.input} w-auto`} value={unitId} onChange={(e) => setUnitId(e.target.value)} aria-label={t("unit")}>
              <option value="">{t("wholeProperty")}</option>
              {units.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.label ?? u.number}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="flex min-w-64 flex-1 flex-col gap-1 text-sm">
          <span className="text-muted">{t("titleField")}</span>
          <input className={ui.input} value={title} maxLength={300} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("submit")}
        </button>
      </form>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {done ? (
        <p className={ui.success} data-testid="dms-upload-done">
          {done.filing?.routed ? t("routed") : t("notRouted")}{" "}
          <Link href={`/dokumente/${done.id}`} className="underline">
            {t("open")}
          </Link>
        </p>
      ) : null}
    </section>
  );
}
