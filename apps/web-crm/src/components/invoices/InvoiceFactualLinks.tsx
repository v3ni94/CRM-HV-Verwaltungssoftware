"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type FactualLinks = {
  work_order_id: string;
  resolution_id: string;
  plan_item_id: string;
  recurring_plan_id: string;
};

export const EMPTY_FACTUAL_LINKS: FactualLinks = {
  work_order_id: "",
  resolution_id: "",
  plan_item_id: "",
  recurring_plan_id: "",
};

type Choice = { id: string; label: string };
type Loaded = { options: Choice[]; error: string | null };
const NONE: Loaded = { options: [], error: null };
const short = (text: string, max = 60) => (text.length > max ? `${text.slice(0, max - 1)}…` : text);

/** M14-02 (T05-Rest, 7.9.1 PÜ02): Auswahlfelder für Auftrag, Beschluss, Wirtschaftsplanposition und
 *  Rechnungsplan in der Rechnungserfassung (`work_order_id`, `resolution_id`, `plan_item_id`,
 *  `recurring_plan_id` an `POST /accounting/invoices`). Alle Angaben sind optional und dienen nur
 *  der sachlichen Prüfung (Hinweise); sie geben nichts frei. Die Listen werden erst beim Öffnen
 *  und je Buchungskreis geladen. Die API prüft, dass die Verknüpfungen zum Mandanten gehören. */
export function InvoiceFactualLinks({
  ledgerId,
  legalEntityId,
  providerId,
  value,
  onChange,
}: {
  ledgerId: string;
  legalEntityId: string | null;
  providerId: string;
  value: FactualLinks;
  onChange: (next: FactualLinks) => void;
}) {
  const t = useTranslations("InvoiceFactualLinks");
  const [open, setOpen] = useState(false);
  const [orders, setOrders] = useState<Loaded>(NONE);
  const [resolutions, setResolutions] = useState<Loaded>(NONE);
  const [plans, setPlans] = useState<Loaded>(NONE);
  const [recurring, setRecurring] = useState<Loaded>(NONE);
  const [planId, setPlanId] = useState("");
  const [items, setItems] = useState<Loaded>(NONE);

  useEffect(() => {
    if (!open || !ledgerId) return;
    let active = true;
    const set = (setter: (l: Loaded) => void) => (l: Loaded) => {
      if (active) setter(l);
    };
    const orderQuery = `page_size=200${providerId ? `&provider_contact_id=${encodeURIComponent(providerId)}` : ""}`;
    void bff<{ id: string; description: string; status: string }[]>(`/api/bff/work-orders?${orderQuery}`).then((r) =>
      set(setOrders)(
        r.ok
          ? { options: r.data.map((o) => ({ id: o.id, label: `${short(o.description ?? "")} (${o.status})` })), error: null }
          : { options: [], error: r.message },
      ),
    );
    if (legalEntityId) {
      void bff<{ id: string; number: number | string; subject: string; decided_on: string | null }[]>(
        `/api/bff/hoa/resolutions?legal_entity_id=${encodeURIComponent(legalEntityId)}`,
      ).then((r) =>
        set(setResolutions)(
          r.ok
            ? {
                options: r.data.map((x) => ({
                  id: x.id,
                  label: `${x.number} ${short(x.subject ?? "")}${x.decided_on ? ` (${formatDate(x.decided_on)})` : ""}`,
                })),
                error: null,
              }
            : { options: [], error: r.message },
        ),
      );
    } else set(setResolutions)(NONE);
    void bff<{ id: string; year: number; version: number; title: string | null; status: string }[]>(
      `/api/bff/hoa/plans?ledger_id=${encodeURIComponent(ledgerId)}`,
    ).then((r) =>
      set(setPlans)(
        r.ok
          ? {
              options: r.data.map((p) => ({
                id: p.id,
                label: `${p.year} Version ${p.version}${p.title ? ` ${short(p.title, 40)}` : ""} (${p.status})`,
              })),
              error: null,
            }
          : { options: [], error: r.message },
      ),
    );
    void bff<{ id: string; text: string; gross: string; ended_at: string | null }[]>(
      `/api/bff/accounting/recurring-invoices?ledger_id=${encodeURIComponent(ledgerId)}&active=true&page_size=500`,
    ).then((r) =>
      set(setRecurring)(
        r.ok
          ? { options: r.data.map((p) => ({ id: p.id, label: `${short(p.text)} (${formatEur(p.gross)})` })), error: null }
          : { options: [], error: r.message },
      ),
    );
    return () => {
      active = false;
    };
  }, [open, ledgerId, legalEntityId, providerId]);

  // Positionen des gewählten Wirtschaftsplans.
  useEffect(() => {
    if (!open || !planId) {
      setItems(NONE);
      return;
    }
    let active = true;
    void bff<{ items: { id: string; label: string; component: string; amount: string }[] }>(`/api/bff/hoa/plans/${planId}`).then((r) => {
      if (!active) return;
      setItems(
        r.ok
          ? { options: r.data.items.map((i) => ({ id: i.id, label: `${short(i.label, 50)} (${formatEur(i.amount)})` })), error: null }
          : { options: [], error: r.message },
      );
    });
    return () => {
      active = false;
    };
  }, [open, planId]);

  // Wechsel des Buchungskreises: Verknüpfungen gehören zum alten Kreis und werden geleert.
  useEffect(() => {
    setPlanId("");
    onChange(EMPTY_FACTUAL_LINKS);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ledgerId]);

  const select = (key: keyof FactualLinks, label: string, loaded: Loaded, extra?: React.ReactNode) => (
    <label className="flex flex-col gap-1">
      <span className={ui.label}>{label}</span>
      <select className={ui.input} value={value[key]} onChange={(e) => onChange({ ...value, [key]: e.target.value })}>
        <option value="">{t("none")}</option>
        {loaded.options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </select>
      {loaded.error ? <span className={ui.error}>{t("loadFailed", { reason: loaded.error })}</span> : null}
      {extra}
    </label>
  );

  return (
    <details data-testid="invoice-factual-links" onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-sm font-medium">{t("title")}</summary>
      <p className={ui.help}>{t("hint")}</p>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        {select("work_order_id", t("workOrder"), orders)}
        {select("resolution_id", t("resolution"), resolutions, legalEntityId ? null : <span className={ui.help}>{t("noEntity")}</span>)}
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("plan")}</span>
          <select
            className={ui.input}
            value={planId}
            onChange={(e) => {
              setPlanId(e.target.value);
              onChange({ ...value, plan_item_id: "" });
            }}
          >
            <option value="">{t("none")}</option>
            {plans.options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
          {plans.error ? <span className={ui.error}>{t("loadFailed", { reason: plans.error })}</span> : null}
        </label>
        {select("plan_item_id", t("planItem"), items, planId ? null : <span className={ui.help}>{t("planFirst")}</span>)}
        {select("recurring_plan_id", t("recurringPlan"), recurring)}
      </div>
    </details>
  );
}
