"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Row = { key: string; value: string; original: boolean };

/** Zusatzfelder am Vertrag pflegen (GAI-415): `PATCH /contracts/{id}/custom-fields` mischt Schlüssel,
 *  ein leerer Wert entfernt das Feld (null). Werte sind Text; die Felddefinition liegt unter Einstellungen. */
export function ContractCustomFieldsForm({ contractId, initial, canEdit }: { contractId: string; initial: Record<string, unknown>; canEdit: boolean }) {
  const t = useTranslations("Aj17.customFields");
  const [rows, setRows] = useState<Row[]>(
    Object.entries(initial ?? {}).map(([key, value]) => ({ key, value: value == null ? "" : String(value), original: true })),
  );
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const update = (i: number, patch: Partial<Row>) => setRows((r) => r.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const save = async () => {
    const payload: Record<string, string | null> = {};
    for (const r of rows) {
      const key = r.key.trim();
      if (!key) continue;
      const value = r.value.trim();
      if (value) payload[key] = value;
      else if (r.original) payload[key] = null;
    }
    setBusy(true);
    setError(null);
    setSaved(false);
    const res = await bff(`/api/bff/contracts/${contractId}/custom-fields`, { method: "PATCH", body: JSON.stringify({ custom_fields: payload }) });
    setBusy(false);
    if (res.ok) setSaved(true);
    else setError(res.message);
  };
  return (
    <section className={`${ui.card} flex flex-col gap-2`} aria-label={t("title")} data-testid="contract-custom-fields">
      <h2 className={ui.h2}>{t("title")}</h2>
      {rows.length === 0 ? <p className="text-sm text-muted">{t("empty")}</p> : null}
      {rows.map((r, i) => (
        <div key={i} className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("key")}</span>
            <input className={ui.input} value={r.key} disabled={!canEdit || r.original} onChange={(e) => update(i, { key: e.target.value })} />
          </label>
          <label className="flex flex-1 flex-col gap-1">
            <span className={ui.label}>{t("value")}</span>
            <input className={ui.input} value={r.value} disabled={!canEdit} onChange={(e) => update(i, { value: e.target.value })} aria-label={`${t("value")} ${r.key}`} />
          </label>
        </div>
      ))}
      <p className={ui.help}>{t("hint")}</p>
      {canEdit ? (
        <div className="flex flex-wrap gap-2">
          <button type="button" className={ui.secondary} onClick={() => setRows((r) => [...r, { key: "", value: "", original: false }])}>
            {t("add")}
          </button>
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void save()}>
            {t("save")}
          </button>
        </div>
      ) : null}
      {saved ? <p role="status" className={ui.success}>{t("saved")}</p> : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
