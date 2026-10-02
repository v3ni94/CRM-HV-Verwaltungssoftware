"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Finding = { rule: string; field: string | null; severity: string; message: string };
const ENTITIES = ["property", "contact", "ticket"] as const;

/** Datenqualität (GAF-26): einzelnen Datensatz gegen die Erfassungsstandards prüfen (ändert nichts)
 *  und Kontaktrollen neu berechnen (Verwaltungsaktion). */
export function DataQualityActions({ canRecompute }: { canRecompute: boolean }) {
  const t = useTranslations("Af20.dq");
  const [entity, setEntity] = useState<(typeof ENTITIES)[number]>("contact");
  const [json, setJson] = useState("{}");
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [changed, setChanged] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const check = async () => {
    setError(null);
    let data: unknown;
    try {
      data = JSON.parse(json);
    } catch {
      setError(t("invalidJson"));
      return;
    }
    setBusy(true);
    const res = await bff<{ findings: Finding[] }>("/api/bff/data-quality/check", { method: "POST", body: JSON.stringify({ entity, data }) });
    setBusy(false);
    if (res.ok) setFindings(res.data.findings);
    else setError(res.message);
  };
  const recompute = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ changed: number }>("/api/bff/contacts/roles/recompute", { method: "POST", body: JSON.stringify({}) });
    setBusy(false);
    if (res.ok) setChanged(res.data.changed);
    else setError(res.message);
  };
  return (
    <section className={ui.card} data-testid="dq-actions">
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("entity")}</span>
          <select className={ui.input} value={entity} onChange={(e) => setEntity(e.target.value as (typeof ENTITIES)[number])}>
            {ENTITIES.map((e) => (
              <option key={e} value={e}>{t(`entities.${e}`)}</option>
            ))}
          </select>
        </label>
        <label className="flex min-w-60 flex-1 flex-col gap-1">
          <span className={ui.label}>{t("data")}</span>
          <textarea className={ui.input} rows={3} value={json} onChange={(e) => setJson(e.target.value)} />
        </label>
        <button type="button" className={ui.primary} disabled={busy} onClick={() => void check()}>
          {t("start")}
        </button>
      </div>
      {findings ? (
        findings.length === 0 ? (
          <p className="mt-2 text-sm text-muted">{t("noFindings")}</p>
        ) : (
          <ul className="mt-2 text-xs text-muted">
            {findings.map((f) => (
              <li key={`${f.rule}-${f.field ?? ""}`}>{f.severity} {f.rule}: {f.message}</li>
            ))}
          </ul>
        )
      ) : null}
      {canRecompute ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button type="button" className={ui.button} disabled={busy} onClick={() => void recompute()}>
            {t("recompute")}
          </button>
          {changed !== null ? <span role="status" className="text-xs text-muted">{t("recomputed", { count: changed })}</span> : null}
        </div>
      ) : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
