"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Occupant = {
  key: string;
  unit_number: string;
  from: string;
  to: string;
  area: string;
  heating: string | null;
  hot_water: string | null;
  heating_kind: string;
  hot_water_kind: string;
  source: string;
  vacancy: boolean;
};
type Co2 = { status: string; tenant_percent?: number; landlord?: string; notes?: string[]; missing?: string[] };
type Result = {
  allocable_costs: string;
  landlord_co2_share: string;
  co2: Co2;
  hot_water_split: { heating_costs: string; hot_water_costs: string; method: string };
  per_occupant: Record<string, { unit_number: string; heating: string; hot_water: string; total: string; vacancy: string; estimated: string }>;
  vacancy_owner_share: string;
  notes: string[];
};
type Heating = {
  total_costs: string | null;
  settings: Record<string, string | number>;
  co2: Record<string, string>;
  consumptions: Record<string, Record<string, string>>;
  result: Result | null;
  result_hash: string | null;
  applied_item_id: string | null;
  tables: { co2_steps: { review_status: string; source: string }; degree_days: { review_status: string; hint?: string } };
  occupants: Occupant[];
};

const CO2_KINDS = ["unknown", "residential", "non_residential", "mixed", "self_supply"] as const;

/** Draft heating statement of an operating cost statement (M17-02): costs and settings,
 *  consumption per occupancy, preview per unit, feed into the statement. Every value is a
 *  draft; issuing the statement stays behind G3. */
export function HeatingPanel({ id, status }: { id: string; status: string }) {
  const t = useTranslations("Billing.heating");
  const tCommon = useTranslations("Common");
  const router = useRouter();
  const [data, setData] = useState<Heating | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [total, setTotal] = useState("");
  const [share, setShare] = useState("70");
  const [hotMethod, setHotMethod] = useState("flat_percent");
  const [hotPercent, setHotPercent] = useState("0");
  const [co2Mode, setCo2Mode] = useState("apply");
  const [co2Kind, setCo2Kind] = useState<string>("unknown");
  const [co2Costs, setCo2Costs] = useState("");
  const [co2Emissions, setCo2Emissions] = useState("");
  const [co2Area, setCo2Area] = useState("");
  const [co2Reason, setCo2Reason] = useState("");
  const [cons, setCons] = useState<Record<string, { heating: string; hot_water: string }>>({});
  const editable = status === "draft";

  const load = async () => {
    const res = await bff<Heating>(`/api/bff/statements/${id}/heating`);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    const d = res.data;
    setData(d);
    setTotal(d.total_costs ?? "");
    setShare(String(d.settings.consumption_share_percent ?? 70));
    setHotMethod(String(d.settings.hot_water_method ?? "flat_percent"));
    setHotPercent(String(d.settings.hot_water_flat_percent ?? "0"));
    setCo2Mode(d.co2.mode ?? "apply");
    setCo2Kind(d.co2.building_kind ?? "unknown");
    setCo2Costs(d.co2.costs ?? "");
    setCo2Emissions(d.co2.emissions_kg ?? "");
    setCo2Area(d.co2.reference_area_m2 ?? "");
    setCo2Reason(d.co2.reason ?? "");
    const next: Record<string, { heating: string; hot_water: string }> = {};
    for (const o of d.occupants) next[o.key] = { heating: o.heating ?? "", hot_water: o.hot_water ?? "" };
    setCons(next);
  };
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const call = async (path: string, method: string, body?: unknown) => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/statements/${id}/heating${path}`, {
      method,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) setError(res.message);
    else await load();
    return res.ok;
  };
  const num = (v: string) => (v.trim() === "" ? undefined : v.replace(",", "."));
  const saveInputs = async () => {
    const co2: Record<string, string | undefined> = { mode: co2Mode, building_kind: co2Kind };
    if (co2Mode === "not_applicable") co2.reason = co2Reason.trim() || undefined;
    else {
      co2.costs = num(co2Costs);
      co2.emissions_kg = num(co2Emissions);
      co2.reference_area_m2 = num(co2Area);
    }
    const settings: Record<string, string | number | undefined> = {
      consumption_share_percent: Number(share),
      hot_water_method: hotMethod,
    };
    if (hotMethod === "flat_percent") settings.hot_water_flat_percent = num(hotPercent) ?? "0";
    const ok = await call("", "PUT", { total_costs: num(total), settings, co2 });
    if (!ok) return;
    const consumptions: Record<string, Record<string, string>> = {};
    for (const [key, v] of Object.entries(cons)) {
      const entry: Record<string, string> = {};
      const h = num(v.heating);
      const w = num(v.hot_water);
      if (h !== undefined) entry.heating = h;
      if (w !== undefined) entry.hot_water = w;
      if (Object.keys(entry).length) consumptions[key] = entry;
    }
    await call("/consumptions", "PUT", { consumptions });
  };
  const result = data?.result ?? null;
  return (
    <section className={ui.card} aria-labelledby="heating-title" data-testid="heating-panel">
      <h2 id="heating-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className={ui.notice}>{t("notice")}</p>
      {data?.tables.degree_days.review_status === "fehlt" ? <p className={ui.help}>{t("degreeDaysMissing")}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {data ? (
        <div className="mt-3 flex flex-col gap-3">
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("totalCosts")}</span>
              <input className={ui.input} value={total} disabled={!editable} onChange={(e) => setTotal(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("share")}</span>
              <input className={ui.input} type="number" min={50} max={70} value={share} disabled={!editable} onChange={(e) => setShare(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("hotWaterMethod")}</span>
              <select className={ui.input} value={hotMethod} disabled={!editable} onChange={(e) => setHotMethod(e.target.value)}>
                <option value="flat_percent">{t("hotWater.flat_percent")}</option>
                <option value="measured">{t("hotWater.measured")}</option>
                <option value="formula">{t("hotWater.formula")}</option>
              </select>
            </label>
            {hotMethod === "flat_percent" ? (
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("hotWaterPercent")}</span>
                <input className={ui.input} value={hotPercent} disabled={!editable} onChange={(e) => setHotPercent(e.target.value)} />
              </label>
            ) : (
              <p className={ui.help}>{t("hotWaterApiOnly")}</p>
            )}
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("co2Mode")}</span>
              <select className={ui.input} value={co2Mode} disabled={!editable} onChange={(e) => setCo2Mode(e.target.value)}>
                <option value="apply">{t("co2.apply")}</option>
                <option value="not_applicable">{t("co2.not_applicable")}</option>
              </select>
            </label>
            {co2Mode === "apply" ? (
              <>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("co2Kind")}</span>
                  <select className={ui.input} value={co2Kind} disabled={!editable} onChange={(e) => setCo2Kind(e.target.value)}>
                    {CO2_KINDS.map((k) => (
                      <option key={k} value={k}>
                        {t(`co2Kinds.${k}`)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("co2Costs")}</span>
                  <input className={ui.input} value={co2Costs} disabled={!editable} onChange={(e) => setCo2Costs(e.target.value)} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("co2Emissions")}</span>
                  <input className={ui.input} value={co2Emissions} disabled={!editable} onChange={(e) => setCo2Emissions(e.target.value)} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("co2Area")}</span>
                  <input className={ui.input} value={co2Area} disabled={!editable} onChange={(e) => setCo2Area(e.target.value)} />
                </label>
              </>
            ) : (
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("co2Reason")}</span>
                <input className={ui.input} value={co2Reason} disabled={!editable} onChange={(e) => setCo2Reason(e.target.value)} />
              </label>
            )}
          </div>
          <h3 className={ui.h3}>{t("consumptions")}</h3>
          <div className="overflow-x-auto">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th>{t("unit")}</th>
                  <th>{t("period")}</th>
                  <th>{t("area")}</th>
                  <th>{t("heatingValue")}</th>
                  <th>{t("hotWaterValue")}</th>
                  <th>{t("source")}</th>
                  {result ? <th className="num">{t("shareResult")}</th> : null}
                </tr>
              </thead>
              <tbody>
                {data.occupants.length === 0 ? (
                  <tr>
                    <td colSpan={99} className="text-muted">
                      {tCommon("emptyList")}
                    </td>
                  </tr>
                ) : null}
                {data.occupants.map((o) => (
                  <tr key={o.key}>
                    <td>
                      {o.unit_number}
                      {o.vacancy ? ` (${t("vacancy")})` : ""}
                    </td>
                    <td>
                      {formatDate(o.from)} bis {formatDate(o.to)}
                    </td>
                    <td className="num">{o.area}</td>
                    <td>
                      <input
                        aria-label={`${t("heatingValue")} ${o.unit_number} ${formatDate(o.from)}`}
                        className={ui.input}
                        value={cons[o.key]?.heating ?? ""}
                        disabled={!editable}
                        onChange={(e) => setCons({ ...cons, [o.key]: { heating: e.target.value, hot_water: cons[o.key]?.hot_water ?? "" } })}
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`${t("hotWaterValue")} ${o.unit_number} ${formatDate(o.from)}`}
                        className={ui.input}
                        value={cons[o.key]?.hot_water ?? ""}
                        disabled={!editable}
                        onChange={(e) => setCons({ ...cons, [o.key]: { heating: cons[o.key]?.heating ?? "", hot_water: e.target.value } })}
                      />
                    </td>
                    <td className="text-muted">
                      {o.source}
                      {o.heating_kind === "estimated" ? ` (${t("estimated")})` : ""}
                    </td>
                    {result ? <td className="num">{formatEur(result.per_occupant[o.key]?.total ?? "0")}</td> : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {editable ? (
            <div className={ui.formActions}>
              <button type="button" className={ui.primary} disabled={busy} onClick={() => void saveInputs()}>
                {t("save")}
              </button>
              <button type="button" className={ui.secondary} disabled={busy} onClick={() => void call("/import-consumptions", "POST", {})}>
                {t("import")}
              </button>
              <button type="button" className={ui.secondary} disabled={busy || !data.total_costs} onClick={() => void call("/calculate", "POST")}>
                {t("calculate")}
              </button>
              <button
                type="button"
                className={ui.secondary}
                disabled={busy || !result || result.co2.status === "pruefen"}
                onClick={() => void call("/apply", "POST").then((ok) => ok && router.refresh())}
              >
                {data.applied_item_id ? t("reapply") : t("apply")}
              </button>
            </div>
          ) : null}
          {result ? (
            <div className="flex flex-col gap-1 text-sm">
              <p>
                {t("summary", {
                  allocable: formatEur(result.allocable_costs),
                  heating: formatEur(result.hot_water_split.heating_costs),
                  hotWater: formatEur(result.hot_water_split.hot_water_costs),
                })}
              </p>
              <p>
                {t("co2Status")}: {t(`co2StatusValues.${result.co2.status}`)}
                {result.co2.tenant_percent !== undefined ? ` (${result.co2.tenant_percent} %, ${t("landlordShare")} ${formatEur(result.landlord_co2_share)})` : ""}
              </p>
              {result.vacancy_owner_share !== "0.00" ? <p>{t("vacancyShare", { amount: formatEur(result.vacancy_owner_share) })}</p> : null}
              {[...result.notes, ...(result.co2.notes ?? [])].map((n) => (
                <p key={n} className={ui.help}>
                  {n}
                </p>
              ))}
              {data.result_hash ? <p className={ui.mono}>{t("trace", { hash: data.result_hash.slice(0, 16) })}</p> : null}
            </div>
          ) : null}
        </div>
      ) : (
        <p className={ui.help}>{t("loading")}</p>
      )}
    </section>
  );
}
