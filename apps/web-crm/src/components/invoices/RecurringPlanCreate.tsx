"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Option = { id: string; label: string };
type Account = { id: string; number: string; name: string };
const MONEY = /^\d+([.,]\d{1,2})?$/;
const UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

/** Q02 (M14-01): Erfassungsmaske für einen neuen Rechnungsplan (POST /accounting/recurring-invoices).
 * Der Plan erzeugt später nur ungeprüfte Rechnungsentwürfe; hier wird nichts gebucht. */
export function RecurringPlanCreate({ ledger, onCreated }: { ledger: string; onCreated: () => void | Promise<void> }) {
  const t = useTranslations("RecurringPlans");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [q, setQ] = useState("");
  const [providers, setProviders] = useState<Option[]>([]);
  const [f, setF] = useState({
    provider: "", account: "", text: "", gross: "", vat_percent: "19", interval_months: "1",
    start_date: "", end_date: "", order_reference: "", service_contract_id: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  // Konten erst beim Öffnen der Maske laden (kein Abruf beim Seitenaufbau).
  const [opened, setOpened] = useState(false);
  useEffect(() => {
    if (!ledger || !opened) return;
    let alive = true;
    void bff<Account[]>(`/api/bff/accounting/ledgers/${ledger}/accounts`).then((res) => {
      if (alive && res.ok) setAccounts(res.data ?? []);
    });
    return () => {
      alive = false;
    };
  }, [ledger, opened]);

  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setDone(false);
    setF((v) => ({ ...v, [k]: e.target.value }));
  };
  const search = async () => {
    const res = await bff<{ items: { id: string; display_name: string }[] }>(`/api/bff/contacts?q=${encodeURIComponent(q.trim())}`);
    if (res.ok) setProviders(res.data.items.map((c) => ({ id: c.id, label: c.display_name })));
  };
  const contractOk = f.service_contract_id.trim() === "" || UUID.test(f.service_contract_id.trim());
  const months = Number(f.interval_months);
  const valid =
    ledger !== "" && f.provider !== "" && f.account !== "" && f.text.trim() !== "" && MONEY.test(f.gross) && Number(f.gross.replace(",", ".")) > 0 &&
    MONEY.test(f.vat_percent) && Number(f.vat_percent.replace(",", ".")) <= 100 && Number.isInteger(months) && months >= 1 && months <= 12 &&
    f.start_date !== "" && (f.end_date === "" || f.end_date >= f.start_date) && contractOk;

  const submit = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ id: string }>("/api/bff/accounting/recurring-invoices", {
      method: "POST",
      body: JSON.stringify({
        ledger_id: ledger,
        provider_contact_id: f.provider,
        account_id: f.account,
        text: f.text.trim(),
        gross: f.gross.replace(",", "."),
        vat_percent: f.vat_percent.replace(",", "."),
        interval_months: months,
        start_date: f.start_date,
        end_date: f.end_date || null,
        order_reference: f.order_reference.trim() || null,
        service_contract_id: f.service_contract_id.trim() || null,
      }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setDone(true);
    setF((v) => ({ ...v, text: "", gross: "", end_date: "", order_reference: "", service_contract_id: "" }));
    await onCreated();
  };

  const input = (k: keyof typeof f, type = "text") => (
    <label className="flex flex-col gap-1">
      <span className={ui.label}>{t(`createFields.${k}`)}</span>
      <input className={ui.input} type={type} value={f[k]} onChange={set(k)} />
    </label>
  );

  return (
    <details className={ui.card} data-testid="plan-create" onToggle={(e) => setOpened((e.currentTarget as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-sm font-medium">{t("createTitle")}</summary>
      <div className="mt-2 grid gap-2 sm:grid-cols-3">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("createFields.provider_search")}</span>
          <span className="flex gap-1">
            <input className={ui.input} value={q} onChange={(e) => setQ(e.target.value)} />
            <button type="button" className={ui.button} onClick={() => void search()} disabled={q.trim().length < 2}>{t("search")}</button>
          </span>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("createFields.provider")}</span>
          <select className={ui.input} value={f.provider} onChange={set("provider")}>
            <option value="">{t("choose")}</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("createFields.account")}</span>
          <select className={ui.input} value={f.account} onChange={set("account")}>
            <option value="">{t("choose")}</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>{`${a.number} ${a.name}`}</option>
            ))}
          </select>
        </label>
        {input("text")}
        {input("gross")}
        {input("vat_percent")}
        {input("interval_months")}
        {input("start_date", "date")}
        {input("end_date", "date")}
        {input("order_reference")}
        {input("service_contract_id")}
      </div>
      <p className={ui.help}>{t("createHint")}</p>
      <button type="button" className={`${ui.primary} mt-2`} onClick={() => void submit()} disabled={busy || !valid}>{t("createSubmit")}</button>
      {done ? <p role="status" className={ui.success}>{t("createdDone")}</p> : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </details>
  );
}
