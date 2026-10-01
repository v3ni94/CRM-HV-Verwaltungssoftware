"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Option = { id: string; label: string };

/** Sammelaktion für Dokumente (M9-04): Kategorie setzen oder mit einem Objekt verknüpfen,
 *  auf die angehakten Zeilen (Checkboxen "bulk-id" im Formular mit der gegebenen Id).
 *  Die Aktion läuft ganz oder gar nicht (POST /workspace/bulk). */
export function DocumentBulkBar({ formId }: { formId: string }) {
  const t = useTranslations("Workspace");
  const router = useRouter();
  const [categories, setCategories] = useState<Option[]>([]);
  const [properties, setProperties] = useState<Option[]>([]);
  const [categoryId, setCategoryId] = useState("");
  const [propertyId, setPropertyId] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      const [cats, props] = await Promise.all([
        bff<{ id: string; name: string }[]>("/api/bff/document-categories"),
        bff<{ items: { id: string; number: string; name: string }[] }>("/api/bff/properties?page_size=200"),
      ]);
      if (!active) return;
      if (cats.ok) setCategories(cats.data.map((c) => ({ id: c.id, label: c.name })));
      if (props.ok) setProperties(props.data.items.map((p) => ({ id: p.id, label: `${p.number} ${p.name}` })));
    })();
    return () => {
      active = false;
    };
  }, []);

  async function run(payload: Record<string, string>) {
    const form = document.getElementById(formId);
    const ids = Array.from(
      new Set(Array.from(form?.querySelectorAll<HTMLInputElement>('input[name="bulk-id"]:checked') ?? []).map((i) => i.value)),
    );
    if (ids.length === 0) {
      setMessage(t("bulkNone"));
      return;
    }
    const result = await bff<{ changed: number }>("/api/bff/workspace/bulk", {
      method: "POST",
      body: JSON.stringify({ ids, ...payload }),
    });
    setMessage(result.ok ? t("bulkDone", { changed: result.data.changed }) : result.message);
    if (result.ok) router.refresh();
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm" role="group" aria-label={t("bulkDocuments")} data-testid="document-bulk-bar">
      <label htmlFor="bulk-category" className="text-muted">
        {t("bulkCategory")}
      </label>
      <select id="bulk-category" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className={`${ui.input} w-48`}>
        <option value="">{t("bulkChoose")}</option>
        {categories.map((c) => (
          <option key={c.id} value={c.id}>
            {c.label}
          </option>
        ))}
      </select>
      <button type="button" className={ui.button} disabled={!categoryId} onClick={() => void run({ action: "documents.set_category", category_id: categoryId })}>
        {t("bulkSetCategory")}
      </button>
      <label htmlFor="bulk-property" className="text-muted">
        {t("bulkProperty")}
      </label>
      <select id="bulk-property" value={propertyId} onChange={(e) => setPropertyId(e.target.value)} className={`${ui.input} w-48`}>
        <option value="">{t("bulkChoose")}</option>
        {properties.map((p) => (
          <option key={p.id} value={p.id}>
            {p.label}
          </option>
        ))}
      </select>
      <button type="button" className={ui.button} disabled={!propertyId} onClick={() => void run({ action: "documents.link_property", property_id: propertyId })}>
        {t("bulkLinkProperty")}
      </button>
      {message ? (
        <span role="status" className="text-muted">
          {message}
        </span>
      ) : null}
    </div>
  );
}
