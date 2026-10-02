"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

export type LicTenant = { id: string; name: string };

export const LICENSE_MODULES = ["core", "rental", "hoa", "accounting", "banking", "portal", "ai"] as const;

type License = {
  id: string;
  module: string;
  unit_quota: number;
  valid_from: string;
  valid_until: string | null;
  price_per_unit: string | null;
  price_source: "license" | "structure";
  min_monthly_amount: string | null;
};

type PriceEntry = { id: string; module: string; price_per_unit: string; valid_from: string; note: string | null };

type BillingLine = {
  module: string;
  units: number;
  price_per_unit: string | null;
  price_source: string;
  tier: string | null;
  trial: boolean;
  amount: string;
  charged: string;
  over_quota: boolean;
};

type Billing = { month: string; lines: BillingLine[]; net_total: string; complete: boolean; note: string };

type UsageRow = { day?: string; month?: string; units: number; users: number; ai_cost_eur: string; storage_bytes: number };
type History = { daily: UsageRow[]; monthly: UsageRow[] };

function toDecimal(value: string): string {
  return value.replace(",", ".").trim();
}

function mb(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toLocaleString("de-DE", { maximumFractionDigits: 1 })} MB`;
}

/** M27-02, M27-03, M27-05: licences, price list, billing preview and usage history. Net
 *  amounts only; the page changes no gate and invents no price. */
export function LicensingAdmin({ tenants, initialPrices }: { tenants: LicTenant[]; initialPrices: PriceEntry[] }) {
  const { busy, guard } = useBusy();
  const t = useTranslations("PlatformLicensing");
  const [tenantId, setTenantId] = useState(tenants[0]?.id ?? "");
  const [licenses, setLicenses] = useState<License[]>([]);
  const [prices, setPrices] = useState<PriceEntry[]>(initialPrices);
  const [billing, setBilling] = useState<Billing | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [error, setError] = useState<string | null>(null);
  const [endDates, setEndDates] = useState<Record<string, string>>({});
  const [form, setForm] = useState({ module: "core", unit_quota: "", valid_from: "", valid_until: "", price: "", minimum: "" });
  const [priceForm, setPriceForm] = useState({ module: "hoa", price: "", valid_from: "", note: "" });

  const loadTenant = useCallback(async (id: string) => {
    if (!id) return;
    const [lic, hist] = await Promise.all([
      bff<License[]>(`/api/bff/platform/licenses?tenant_id=${id}`),
      bff<History>(`/api/bff/platform/tenants/${id}/usage/history`),
    ]);
    if (lic.ok) setLicenses(lic.data);
    else setError(lic.message);
    if (hist.ok) setHistory(hist.data);
  }, []);

  useEffect(() => {
    void loadTenant(tenantId);
  }, [tenantId, loadTenant]);

  async function reloadPrices() {
    const res = await bff<PriceEntry[]>("/api/bff/platform/price-list");
    if (res.ok) setPrices(res.data);
  }

  async function run<T>(action: Promise<{ ok: boolean; message?: string } & Partial<{ data: T }>>) {
    setError(null);
    const res = await action;
    if (!res.ok) setError(res.message ?? null);
    return res.ok;
  }

  async function createLicense() {
    const body: Record<string, unknown> = {
      tenant_id: tenantId,
      module: form.module,
      unit_quota: Number.parseInt(form.unit_quota || "0", 10),
      valid_from: form.valid_from,
    };
    if (form.valid_until) body.valid_until = form.valid_until;
    if (form.price) body.price_per_unit = toDecimal(form.price);
    if (form.minimum) body.min_monthly_amount = toDecimal(form.minimum);
    if (await run(bff("/api/bff/platform/licenses", { method: "POST", body: JSON.stringify(body) }))) {
      setForm({ ...form, unit_quota: "", valid_from: "", valid_until: "", price: "", minimum: "" });
      await loadTenant(tenantId);
    }
  }

  async function endLicense(id: string) {
    const until = endDates[id];
    if (!until) return;
    if (await run(bff(`/api/bff/platform/licenses/${id}/end`, { method: "POST", body: JSON.stringify({ valid_until: until }) }))) {
      await loadTenant(tenantId);
    }
  }

  async function applyStructure(id: string) {
    if (await run(bff(`/api/bff/platform/licenses/${id}`, { method: "PATCH", body: JSON.stringify({ use_structure_price: true }) }))) {
      await loadTenant(tenantId);
    }
  }

  async function addPrice() {
    const body: Record<string, unknown> = {
      module: priceForm.module,
      price_per_unit: toDecimal(priceForm.price),
      valid_from: priceForm.valid_from,
    };
    if (priceForm.note) body.note = priceForm.note;
    if (await run(bff("/api/bff/platform/price-list", { method: "POST", body: JSON.stringify(body) }))) {
      setPriceForm({ ...priceForm, price: "", valid_from: "", note: "" });
      await reloadPrices();
    }
  }

  async function changePrice(entry: PriceEntry) {
    const next = window.prompt(t("pricePrompt"), entry.price_per_unit.replace(".", ","));
    if (next === null) return;
    if (await run(bff(`/api/bff/platform/price-list/${entry.id}`, { method: "PATCH", body: JSON.stringify({ price_per_unit: toDecimal(next) }) }))) {
      await reloadPrices();
    }
  }

  async function deletePrice(entry: PriceEntry) {
    if (!window.confirm(t("confirmDelete"))) return;
    if (await run(bff(`/api/bff/platform/price-list/${entry.id}`, { method: "DELETE" }))) await reloadPrices();
  }

  async function preview() {
    setError(null);
    const res = await bff<Billing>(`/api/bff/platform/tenants/${tenantId}/billing-preview?month=${month}-01`);
    if (res.ok) setBilling(res.data);
    else setError(res.message);
  }

  async function countNow() {
    if (await run(bff(`/api/bff/platform/tenants/${tenantId}/usage`, { method: "POST", body: JSON.stringify({ month: `${new Date().toISOString().slice(0, 7)}-01` }) }))) {
      await loadTenant(tenantId);
    }
  }

  return (
    <div className={ui.sectionGap}>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}

      <section className={`${ui.card} flex flex-col gap-3`}>
        <h2 className={ui.h2}>{t("licenses")}</h2>
        <label className="flex flex-col gap-1 sm:max-w-sm">
          <span className={ui.label}>{t("tenant")}</span>
          <select className={ui.input} value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
            {tenants.map((tn) => (
              <option key={tn.id} value={tn.id}>
                {tn.name}
              </option>
            ))}
          </select>
        </label>
        {licenses.length ? (
          <div className={ui.tableScroll}>
            <table className={`${ui.table} w-full text-sm`}>
              <thead>
                <tr>
                  <th className="text-left">{t("module")}</th>
                  <th className="text-left">{t("quota")}</th>
                  <th className="text-left">{t("validFrom")}</th>
                  <th className="text-left">{t("validUntil")}</th>
                  <th className="text-left">{t("price")}</th>
                  <th className="text-left">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {licenses.map((l) => (
                  <tr key={l.id}>
                    <td>{t(`module_${l.module}`)}</td>
                    <td>{l.unit_quota}</td>
                    <td>{formatDate(l.valid_from)}</td>
                    <td>{l.valid_until ? formatDate(l.valid_until) : t("unlimited")}</td>
                    <td>
                      {l.price_per_unit !== null ? formatEur(l.price_per_unit) : t("fromStructure")}
                      {l.min_monthly_amount ? ` (${t("minimum")} ${formatEur(l.min_monthly_amount)})` : ""}
                    </td>
                    <td className="flex flex-wrap items-center gap-2">
                      <input
                        type="date"
                        aria-label={`${t("endDate")} ${t(`module_${l.module}`)}`}
                        className={ui.input}
                        value={endDates[l.id] ?? ""}
                        onChange={(e) => setEndDates({ ...endDates, [l.id]: e.target.value })}
                      />
                      <button type="button" className={ui.buttonSm} disabled={busy || (!endDates[l.id])} onClick={guard(() => endLicense(l.id))}>
                        {t("end")}
                      </button>
                      {l.price_per_unit !== null ? (
                        <button disabled={busy} type="button" className={ui.buttonSm} onClick={guard(() => applyStructure(l.id))}>
                          {t("useStructure")}
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className={ui.help}>{t("noLicenses")}</p>
        )}
        <h3 className="text-sm font-semibold">{t("createTitle")}</h3>
        <div className="grid gap-2 sm:grid-cols-3">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("module")}</span>
            <select className={ui.input} value={form.module} onChange={(e) => setForm({ ...form, module: e.target.value })}>
              {LICENSE_MODULES.map((m) => (
                <option key={m} value={m}>
                  {t(`module_${m}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("quota")}</span>
            <input className={ui.input} inputMode="numeric" value={form.unit_quota} onChange={(e) => setForm({ ...form, unit_quota: e.target.value.replace(/\D/g, "") })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("validFrom")}</span>
            <input type="date" className={ui.input} value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("validUntil")}</span>
            <input type="date" className={ui.input} value={form.valid_until} onChange={(e) => setForm({ ...form, valid_until: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("agreedPrice")}</span>
            <input className={ui.input} inputMode="decimal" placeholder={t("fromStructure")} value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("minimum")}</span>
            <input className={ui.input} inputMode="decimal" value={form.minimum} onChange={(e) => setForm({ ...form, minimum: e.target.value })} />
          </label>
        </div>
        <div className={ui.formActions}>
          <button type="button" className={ui.primary} disabled={busy || (!tenantId || !form.valid_from || !form.unit_quota)} onClick={guard(() => createLicense())}>
            {t("create")}
          </button>
        </div>
      </section>

      <section className={`${ui.card} flex flex-col gap-3`}>
        <h2 className={ui.h2}>{t("billingTitle")}</h2>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("month")}</span>
            <input type="month" className={ui.input} value={month} onChange={(e) => setMonth(e.target.value)} />
          </label>
          <button type="button" className={ui.secondary} disabled={busy || (!tenantId || !month)} onClick={guard(() => preview())}>
            {t("calculate")}
          </button>
        </div>
        {billing ? (
          <>
            {billing.complete ? null : <p className={ui.warning}>{t("incomplete")}</p>}
            <div className={ui.tableScroll}>
              <table className={`${ui.table} w-full text-sm`}>
                <thead>
                  <tr>
                    <th className="text-left">{t("module")}</th>
                    <th className="text-left">{t("units")}</th>
                    <th className="text-left">{t("price")}</th>
                    <th className="text-left">{t("amount")}</th>
                    <th className="text-left">{t("charged")}</th>
                  </tr>
                </thead>
                <tbody>
                  {billing.lines.map((l) => (
                    <tr key={l.module}>
                      <td>
                        {t(`module_${l.module}`)}
                        {l.tier ? ` (${l.tier})` : ""}
                        {l.trial ? <span className={`${ui.badgeSuccess} ml-2`}>{t("trial")}</span> : null}
                        {l.over_quota ? <span className={`${ui.badgeWarning} ml-2`}>{t("overQuota")}</span> : null}
                      </td>
                      <td>{l.units}</td>
                      <td>{l.price_per_unit !== null ? formatEur(l.price_per_unit) : t("open")}</td>
                      <td>{formatEur(l.amount)}</td>
                      <td>{formatEur(l.charged)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-sm font-semibold">
              {t("netTotal")}: {formatEur(billing.net_total)}
            </p>
            <p className={ui.help}>{billing.note}</p>
          </>
        ) : null}
      </section>

      <section className={`${ui.card} flex flex-col gap-3`}>
        <h2 className={ui.h2}>{t("usageTitle")}</h2>
        <div>
          <button type="button" className={ui.secondary} disabled={busy || (!tenantId)} onClick={guard(() => countNow())}>
            {t("countNow")}
          </button>
        </div>
        {history && (history.daily.length || history.monthly.length) ? (
          <div className="grid gap-4 lg:grid-cols-2">
            {([
              ["monthly", history.monthly, "month"],
              ["daily", history.daily.slice(-31), "day"],
            ] as const).map(([key, rows, field]) => (
              <div key={key} className={ui.tableScroll}>
                <table className={`${ui.table} w-full text-sm`}>
                  <caption className="text-left text-xs text-muted">{t(key)}</caption>
                  <thead>
                    <tr>
                      <th className="text-left">{t(field)}</th>
                      <th className="text-left">{t("units")}</th>
                      <th className="text-left">{t("users")}</th>
                      <th className="text-left">{t("aiCost")}</th>
                      <th className="text-left">{t("storage")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r[field] ?? ""}>
                        <td>{formatDate(r[field])}</td>
                        <td>{r.units}</td>
                        <td>{r.users}</td>
                        <td>{formatEur(r.ai_cost_eur)}</td>
                        <td>{mb(r.storage_bytes)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        ) : (
          <p className={ui.help}>{t("noUsage")}</p>
        )}
      </section>

      <section className={`${ui.card} flex flex-col gap-3`}>
        <h2 className={ui.h2}>{t("priceListTitle")}</h2>
        <p className={ui.help}>{t("priceListHint")}</p>
        {prices.length ? (
          <div className={ui.tableScroll}>
            <table className={`${ui.table} w-full text-sm`}>
              <thead>
                <tr>
                  <th className="text-left">{t("module")}</th>
                  <th className="text-left">{t("validFrom")}</th>
                  <th className="text-left">{t("price")}</th>
                  <th className="text-left">{t("note")}</th>
                  <th className="text-left">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {prices.map((p) => (
                  <tr key={p.id}>
                    <td>{t(`module_${p.module}`)}</td>
                    <td>{formatDate(p.valid_from)}</td>
                    <td>{formatEur(p.price_per_unit)}</td>
                    <td>{p.note ?? ""}</td>
                    <td className="flex gap-2">
                      <button disabled={busy} type="button" className={ui.buttonSm} onClick={guard(() => changePrice(p))}>
                        {t("change")}
                      </button>
                      <button disabled={busy} type="button" className={ui.buttonSm} onClick={guard(() => deletePrice(p))}>
                        {t("delete")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className={ui.help}>{t("noPrices")}</p>
        )}
        <div className="grid gap-2 sm:grid-cols-4">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("module")}</span>
            <select className={ui.input} value={priceForm.module} onChange={(e) => setPriceForm({ ...priceForm, module: e.target.value })}>
              {LICENSE_MODULES.map((m) => (
                <option key={m} value={m}>
                  {t(`module_${m}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("price")}</span>
            <input className={ui.input} inputMode="decimal" value={priceForm.price} onChange={(e) => setPriceForm({ ...priceForm, price: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("validFrom")}</span>
            <input type="date" className={ui.input} value={priceForm.valid_from} onChange={(e) => setPriceForm({ ...priceForm, valid_from: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("note")}</span>
            <input className={ui.input} value={priceForm.note} onChange={(e) => setPriceForm({ ...priceForm, note: e.target.value })} />
          </label>
        </div>
        <div className={ui.formActions}>
          <button type="button" className={ui.primary} disabled={busy || (!priceForm.price || !priceForm.valid_from)} onClick={guard(() => addPrice())}>
            {t("addPrice")}
          </button>
        </div>
      </section>
    </div>
  );
}
