"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

import { ConsumptionInfoDeliveryForm } from "./ConsumptionInfoDeliveryForm";

type Settings = {
  property_id: string;
  enabled: boolean;
  tenant_enabled: boolean;
  notifications_enabled: boolean;
  template_verified: boolean;
  rule_version: string;
};
type MonthRow = { month: string; units: number; incomplete: number; not_stored: number };
type Component = { value: string; unit_of_measure: string; kind: string; source: string } | null;
type InfoRow = {
  id: string;
  unit_id: string;
  month: string;
  values: { heating?: Component; hot_water?: Component };
  missing: string[];
  missing_labels: string[];
  to_verify: { key: string; label: string; status: string }[];
  trigger: string;
  document_id: string | null;
  created_at: string;
};
type Listing = {
  settings: Settings;
  months: MonthRow[];
  rows: InfoRow[];
  to_verify: { key: string; label: string; status: string }[];
};

function value(component: Component | undefined): string {
  if (!component) return "";
  const number = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(Number(component.value));
  return `${number} ${component.unit_of_measure}${component.kind === "estimated" ? " (geschätzt)" : ""}`;
}

/** Verbrauchsinformation nach § 6a HeizkostenV je Objekt (Regel H03): erzeugte Monate mit
 *  fehlenden Daten, Objektschalter, manueller Lauf für einen Monat und die Liste der vom
 *  Betreiber zu verifizierenden Inhalte. Lesen braucht accounting:read, Schalter und Lauf
 *  properties:update. Mieter sehen erst etwas, wenn die Vorlage als verifiziert markiert ist
 *  (Mandanteneinstellung). */
export function ConsumptionInfoPanel({ propertyId, permissions }: { propertyId: string; permissions: string[] }) {
  const t = useTranslations("ConsumptionInfo");
  const canRead = permissions.includes("accounting:read");
  const canUpdate = permissions.includes("properties:update");
  const [data, setData] = useState<Listing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [month, setMonth] = useState(() => {
    const now = new Date();
    const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    return `${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, "0")}`;
  });
  const [result, setResult] = useState<string | null>(null);
  const base = `/api/bff/properties/${propertyId}/consumption-info`;

  const load = useCallback(async () => {
    const res = await bff<Listing>(base);
    if (res.ok) {
      setData(res.data);
      setError(null);
    } else setError(res.message);
  }, [base]);

  useEffect(() => {
    if (canRead) void load();
  }, [canRead, load]);

  async function toggle(next: boolean) {
    setBusy(true);
    const res = await bff<Settings>(`${base}/settings`, { method: "PUT", body: JSON.stringify({ enabled: next }) });
    setBusy(false);
    if (res.ok) setData((d) => (d ? { ...d, settings: res.data } : d));
    else setError(res.message);
  }

  async function run(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setResult(null);
    const res = await bff<{ month: string; created: number; skipped: number; incomplete: number; notified: number }>(`${base}/run`, {
      method: "POST",
      body: JSON.stringify({ month: `${month}-01` }),
    });
    setBusy(false);
    if (res.ok) {
      setResult(t("runResult", { month: formatDate(res.data.month), created: res.data.created, skipped: res.data.skipped, incomplete: res.data.incomplete }));
      await load();
    } else setError(res.message);
  }

  if (!canRead) return null;
  const s = data?.settings;
  const active = Boolean(s?.enabled && s?.tenant_enabled);
  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="consumption-info-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="consumption-info-title" className={ui.h2}>
          {t("title")}
        </h2>
        {s ? (
          <span className={active ? ui.badgeSuccess : ui.badge} data-testid="consumption-info-status">
            {active ? t("status.on") : t("status.off")}
          </span>
        ) : null}
      </div>
      <p className={ui.help}>{t("description")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {s ? (
        <>
          {!s.tenant_enabled ? <p className={ui.notice}>{t("tenantOff")}</p> : null}
          {!s.template_verified ? <p className={ui.warning}>{t("notVerified")}</p> : null}
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={s.enabled} disabled={!canUpdate || busy} onChange={(e) => void toggle(e.target.checked)} data-testid="consumption-info-switch" />
            <span>{t("propertySwitch")}</span>
          </label>
          {canUpdate ? (
            <form onSubmit={run} className="flex flex-wrap items-end gap-2">
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("month")}</span>
                <input className={ui.input} type="month" value={month} onChange={(e) => setMonth(e.target.value)} data-testid="consumption-info-month" />
              </label>
              <button type="submit" className={ui.primary} disabled={busy || !active}>
                {t("run")}
              </button>
            </form>
          ) : null}
          {result ? <p className={ui.success}>{result}</p> : null}
        </>
      ) : null}
      {data ? (
        <>
          <h3 className={ui.h3}>{t("months")}</h3>
          {data.months.length === 0 ? (
            <p className={ui.help}>{t("empty")}</p>
          ) : (
            <div className={ui.tableScroll}>
              <table className={ui.table}>
                <thead>
                  <tr>
                    <th scope="col">{t("columns.month")}</th>
                    <th scope="col" className="num">{t("columns.units")}</th>
                    <th scope="col" className="num">{t("columns.incomplete")}</th>
                    <th scope="col" className="num">{t("columns.notStored")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.months.map((m) => (
                    <tr key={m.month}>
                      <td>{formatDate(m.month).slice(3)}</td>
                      <td className="num">{m.units}</td>
                      <td className="num">{m.incomplete}</td>
                      <td className="num">{m.not_stored}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data.rows.length > 0 ? (
            <details>
              <summary className="cursor-pointer text-sm">{t("rows", { count: data.rows.length })}</summary>
              <div className={ui.tableScroll}>
                <table className={ui.table}>
                  <thead>
                    <tr>
                      <th scope="col">{t("columns.month")}</th>
                      <th scope="col">{t("columns.unit")}</th>
                      <th scope="col">{t("columns.heating")}</th>
                      <th scope="col">{t("columns.hotWater")}</th>
                      <th scope="col">{t("columns.missing")}</th>
                      <th scope="col">{t("columns.created")}</th>
                      <th scope="col">{t("columns.delivery")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((r) => (
                      <tr key={r.id}>
                        <td>{formatDate(r.month).slice(3)}</td>
                        <td className="font-mono text-xs">{r.unit_id.slice(0, 8)}</td>
                        <td>{value(r.values.heating)}</td>
                        <td>{value(r.values.hot_water)}</td>
                        <td>{r.missing_labels.join(", ")}</td>
                        <td>{formatDateTime(r.created_at)}</td>
                        <td>
                          <ConsumptionInfoDeliveryForm propertyId={propertyId} infoId={r.id} canUpdate={canUpdate} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          ) : null}
          <h3 className={ui.h3}>{t("toVerifyTitle")}</h3>
          <p className={ui.help}>{t("toVerifyHint")}</p>
          <ul className="flex flex-col gap-1 text-sm" data-testid="consumption-info-to-verify">
            {data.to_verify.map((item) => (
              <li key={item.key}>
                <span className={ui.badgeWarning}>{item.status}</span> {item.label}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
