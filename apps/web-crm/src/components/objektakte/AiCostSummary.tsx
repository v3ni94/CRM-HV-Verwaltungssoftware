"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import type { PropertyOption } from "./ObjektakteLists";

type Totals = { calls: number; tokens_in: number; tokens_out: number; cost_eur: string };
export type AiCostSummaryOut = {
  property_id: string | null;
  from: string | null;
  to: string | null;
  by_property: (Totals & { property_id: string | null; property_number: string | null; property_name: string | null })[];
  by_month: (Totals & { month: string })[];
  total: Totals;
};

function formatMonth(month: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  return match ? `${match[2]}.${match[1]}` : month;
}

/** M35 Stufe 4 follow-up: cost evaluation of the taken over objektakte AI call protocol per
 * property and per month (`GET /api/v1/objektakte/ai-calls/summary`), read only. */
export function AiCostSummary({ properties }: { properties: PropertyOption[] }) {
  const t = useTranslations("Objektakte.aiCosts");
  const [propertyId, setPropertyId] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [applied, setApplied] = useState({ propertyId: "", from: "", to: "" });
  const [data, setData] = useState<AiCostSummaryOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      const params = new URLSearchParams();
      if (applied.propertyId) params.set("property_id", applied.propertyId);
      if (applied.from) params.set("from", applied.from);
      if (applied.to) params.set("to", applied.to);
      const query = params.toString();
      const res = await bff<AiCostSummaryOut>(`/api/bff/objektakte/ai-calls/summary${query ? `?${query}` : ""}`);
      if (cancelled) return;
      if (res.ok) setData(res.data);
      else setError(res.message);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [applied]);

  const propertyLabel = (row: AiCostSummaryOut["by_property"][number]) =>
    row.property_id ? `${row.property_number ?? ""} ${row.property_name ?? ""}`.trim() : t("withoutProperty");

  return (
    <section className={`${ui.card} flex flex-col gap-4`} aria-label={t("title")}>
      <div className="flex flex-col gap-1">
        <h2 className={ui.h2}>{t("title")}</h2>
        <p className={ui.help}>{t("intro")}</p>
      </div>

      <form
        className="grid gap-3 sm:grid-cols-4"
        onSubmit={(e) => {
          e.preventDefault();
          setApplied({ propertyId, from, to });
        }}
      >
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("property")}</span>
          <select className={ui.input} value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
            <option value="">{t("allProperties")}</option>
            {properties.map((p) => (
              <option key={p.id} value={p.id}>
                {p.number} {p.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("from")}</span>
          <input type="date" className={ui.input} value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("to")}</span>
          <input type="date" className={ui.input} value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
        <div className="flex items-end">
          <button type="submit" className={`${ui.secondary} ${ui.actionFull}`} disabled={loading}>
            {t("apply")}
          </button>
        </div>
      </form>

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {loading ? <p className={ui.help}>{t("loading")}</p> : null}

      {data && !loading ? (
        data.total.calls === 0 ? (
          <p className="text-sm text-muted">{t("empty")}</p>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">{t("byProperty")}</h3>
              <div className="overflow-x-auto">
                <table className={ui.table} data-testid="ai-costs-by-property">
                  <thead>
                    <tr>
                      <th scope="col">{t("colProperty")}</th>
                      <th scope="col">{t("colCalls")}</th>
                      <th scope="col">{t("colTokensIn")}</th>
                      <th scope="col">{t("colTokensOut")}</th>
                      <th scope="col">{t("colCost")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_property.map((row) => (
                      <tr key={row.property_id ?? "none"}>
                        <td>{propertyLabel(row)}</td>
                        <td>{row.calls}</td>
                        <td>{row.tokens_in}</td>
                        <td>{row.tokens_out}</td>
                        <td>{formatEur(row.cost_eur)}</td>
                      </tr>
                    ))}
                    <tr className="font-semibold">
                      <td>{t("total")}</td>
                      <td>{data.total.calls}</td>
                      <td>{data.total.tokens_in}</td>
                      <td>{data.total.tokens_out}</td>
                      <td>{formatEur(data.total.cost_eur)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">{t("byMonth")}</h3>
              <div className="overflow-x-auto">
                <table className={ui.table} data-testid="ai-costs-by-month">
                  <thead>
                    <tr>
                      <th scope="col">{t("colMonth")}</th>
                      <th scope="col">{t("colCalls")}</th>
                      <th scope="col">{t("colTokensIn")}</th>
                      <th scope="col">{t("colTokensOut")}</th>
                      <th scope="col">{t("colCost")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_month.map((row) => (
                      <tr key={row.month}>
                        <td>{formatMonth(row.month)}</td>
                        <td>{row.calls}</td>
                        <td>{row.tokens_in}</td>
                        <td>{row.tokens_out}</td>
                        <td>{formatEur(row.cost_eur)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )
      ) : null}
    </section>
  );
}
