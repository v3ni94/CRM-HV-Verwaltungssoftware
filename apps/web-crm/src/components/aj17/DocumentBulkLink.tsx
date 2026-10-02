"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const BULK_LINK_ENTITY_TYPES = ["property", "unit", "contract", "ticket"] as const;
type Item = { id: string; ok: boolean; code?: string | null; detail?: string | null };
type Out = { total: number; succeeded: number; failed: number; items: Item[] };

/** Mehrere Dokumente mit einem Objekt verknüpfen (GAI-417): `POST /documents/bulk-link`, Teilerfolgsbericht
 *  je Dokument. Reine Verknüpfung, keine Buchungswirkung. Recht documents:update. */
export function DocumentBulkLink({ canEdit, initialIds = [] }: { canEdit: boolean; initialIds?: string[] }) {
  const t = useTranslations("Aj17.docs");
  const [ids, setIds] = useState(initialIds.join("\n"));
  const [entityType, setEntityType] = useState<string>("property");
  const [entityId, setEntityId] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Out | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!canEdit) return null;
  const submit = async () => {
    const list = ids.split(/[\s,;]+/).filter(Boolean);
    if (list.length === 0 || !list.every((x) => UUID.test(x)) || !UUID.test(entityId.trim())) {
      setError(t("invalid"));
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    const res = await bff<Out>("/api/bff/documents/bulk-link", {
      method: "POST",
      body: JSON.stringify({ ids: list, entity_type: entityType, entity_id: entityId.trim() }),
    });
    setBusy(false);
    if (res.ok) setResult(res.data);
    else setError(res.message);
  };
  return (
    <section className={`${ui.card} flex flex-col gap-2`} aria-label={t("bulkTitle")} data-testid="document-bulk-link">
      <h2 className={ui.h2}>{t("bulkTitle")}</h2>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("ids")}</span>
        <textarea className={ui.input} rows={3} value={ids} onChange={(e) => setIds(e.target.value)} />
      </label>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("entityType")}</span>
          <select className={ui.input} value={entityType} onChange={(e) => setEntityType(e.target.value)}>
            {BULK_LINK_ENTITY_TYPES.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-1 flex-col gap-1">
          <span className={ui.label}>{t("entityId")}</span>
          <input className={ui.input} value={entityId} onChange={(e) => setEntityId(e.target.value)} />
        </label>
        <button type="button" className={ui.primary} disabled={busy} onClick={() => void submit()}>
          {t("submit")}
        </button>
      </div>
      {result ? (
        <div role="status" data-testid="bulk-link-result">
          <p className="text-sm">{t("result", { succeeded: result.succeeded, total: result.total, failed: result.failed })}</p>
          <ul className="text-xs text-muted">
            {result.items
              .filter((i) => !i.ok)
              .map((i) => (
                <li key={i.id}>{t("failedItem", { id: i.id, detail: i.detail ?? i.code ?? "" })}</li>
              ))}
          </ul>
        </div>
      ) : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
