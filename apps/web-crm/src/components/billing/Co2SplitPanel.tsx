"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Co2Result = { tenant_percent: number; tenant: string; landlord: string; rule_version: string; note: string };

const DECIMAL = /^\d+([.,]\d{1,4})?$/;

/** GAF-13, GAG-11: CO2 cost split for residential buildings (POST statements/co2-split).
 *  Calculation only: nothing is stored or posted; applicability per building is checked by the
 *  user (H04). The statement itself stays behind G3. */
export function Co2SplitPanel() {
  const t = useTranslations("BillingExtra.co2Split");
  const [emissions, setEmissions] = useState("");
  const [costs, setCosts] = useState("");
  const [result, setResult] = useState<Co2Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const valid = DECIMAL.test(emissions) && /^\d+([.,]\d{1,2})?$/.test(costs);
  const calculate = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    const res = await bff<Co2Result>("/api/bff/statements/co2-split", {
      method: "POST",
      body: JSON.stringify({ specific_emissions: emissions.replace(",", "."), costs: costs.replace(",", ".") }),
    });
    setBusy(false);
    if (res.ok) setResult(res.data ?? null);
    else setError(res.message);
  };
  return (
    <section className="flex flex-col gap-2" data-testid="co2-split">
      <h3 className={ui.h2}>{t("title")}</h3>
      <p className={ui.help}>{t("notice")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("emissions")}</span>
          <input className={ui.input} inputMode="decimal" value={emissions} onChange={(e) => setEmissions(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("costs")}</span>
          <input className={ui.input} inputMode="decimal" value={costs} onChange={(e) => setCosts(e.target.value)} />
        </label>
        <button type="button" className={ui.button} onClick={calculate} disabled={busy || !valid}>
          {t("calculate")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {result ? (
        <dl className="grid grid-cols-2 gap-1 text-sm" data-testid="co2-result">
          <dt>{t("tenantPercent")}</dt>
          <dd>{result.tenant_percent} %</dd>
          <dt>{t("tenant")}</dt>
          <dd>{formatEur(result.tenant)}</dd>
          <dt>{t("landlord")}</dt>
          <dd>{formatEur(result.landlord)}</dd>
          <dt>{t("ruleVersion")}</dt>
          <dd>{result.rule_version}</dd>
          <dd className="col-span-2 text-muted">{result.note}</dd>
        </dl>
      ) : null}
    </section>
  );
}
