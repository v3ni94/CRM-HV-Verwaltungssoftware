"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type PricingItem = {
  id: string;
  kind: "tier" | "module" | "trial";
  code: string;
  label: string;
  min_units: number | null;
  max_units: number | null;
  amount: string | null;
  unit: string;
  trial_days: number | null;
  sort_order: number;
  active: boolean;
  amount_missing: boolean;
};

export type Pricing = { items: PricingItem[]; complete: boolean; missing_amounts: string[] };

/** M27-01: pricing structure (tiers by units, module add-ons, trial). Amounts are empty until
 *  the operator maintains them; the offer PDF is a draft. No amount is invented here. */
export function PricingAdmin({ initial }: { initial: Pricing }) {
  const t = useTranslations("PlatformPricing");
  const [pricing, setPricing] = useState<Pricing>(initial);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [customer, setCustomer] = useState("");
  const [units, setUnits] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    const res = await bff<Pricing>("/api/bff/platform/pricing");
    if (res.ok) setPricing(res.data);
  }

  async function save(item: PricingItem, field: Record<string, unknown>) {
    setError(null);
    const res = await bff<PricingItem>(`/api/bff/platform/pricing/items/${item.id}`, {
      method: "PATCH",
      body: JSON.stringify(field),
    });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    await reload();
  }

  const offerHref = `/api/bff/platform/pricing/offer.pdf?customer_name=${encodeURIComponent(customer || t("customerDefault"))}${units ? `&units=${encodeURIComponent(units)}` : ""}`;
  const groups: PricingItem["kind"][] = ["tier", "module", "trial"];

  return (
    <div className={ui.sectionGap}>
      <p className={pricing.complete ? ui.success : ui.warning}>
        {pricing.complete ? t("complete") : t("incomplete", { count: pricing.missing_amounts.length })}
      </p>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {groups.map((kind) => (
        <section key={kind} className={ui.card}>
          <h2 className={ui.h2}>{t(`kind_${kind}`)}</h2>
          <table className={`${ui.table} mt-2 w-full text-sm`}>
            <thead>
              <tr>
                <th className="text-left">{t("label")}</th>
                <th className="text-left">{t("range")}</th>
                <th className="text-left">{t("amount")}</th>
                <th className="text-left">{t("unit")}</th>
                <th className="text-left">{t("actions")}</th>
              </tr>
            </thead>
            <tbody>
              {pricing.items
                .filter((i) => i.kind === kind)
                .map((item) => (
                  <tr key={item.id} className={item.active ? "" : "opacity-60"}>
                    <td>{item.label}</td>
                    <td>
                      {item.kind === "tier"
                        ? `${item.min_units ?? 0} ${item.max_units !== null ? t("upTo", { max: item.max_units }) : t("andMore")}`
                        : item.kind === "trial"
                          ? item.trial_days !== null
                            ? t("days", { days: item.trial_days })
                            : t("open")
                          : ""}
                    </td>
                    <td>
                      <input
                        aria-label={`${t("amount")} ${item.label}`}
                        className={`${ui.input} w-28`}
                        inputMode="decimal"
                        placeholder={t("open")}
                        value={drafts[item.id] ?? item.amount ?? ""}
                        onChange={(e) => setDrafts({ ...drafts, [item.id]: e.target.value })}
                      />
                      {item.amount_missing ? <span className={`${ui.badgeWarning} ml-2`}>{t("missing")}</span> : null}
                    </td>
                    <td>{t(`unit_${item.unit}`)}</td>
                    <td className="flex gap-2">
                      <button
                        type="button"
                        className={ui.buttonSm}
                        onClick={() => {
                          const raw = (drafts[item.id] ?? item.amount ?? "").replace(",", ".").trim();
                          void save(item, raw ? { amount: raw } : { clear_amount: true });
                        }}
                      >
                        {t("save")}
                      </button>
                      <button type="button" className={ui.buttonSm} onClick={() => void save(item, { active: !item.active })}>
                        {item.active ? t("deactivate") : t("activate")}
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </section>
      ))}
      <section className={`${ui.card} flex flex-col gap-3 sm:max-w-md`}>
        <h2 className={ui.h2}>{t("offerTitle")}</h2>
        <p className={ui.help}>{t("offerHint")}</p>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("customer")}</span>
          <input className={ui.input} value={customer} onChange={(e) => setCustomer(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("units")}</span>
          <input className={ui.input} inputMode="numeric" value={units} onChange={(e) => setUnits(e.target.value.replace(/\D/g, ""))} />
        </label>
        <a className={ui.secondary} href={offerHref} download>
          {t("offerDownload")}
        </a>
      </section>
    </div>
  );
}
