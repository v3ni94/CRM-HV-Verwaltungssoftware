"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Ledger = { id: string; name: string };
type CatalogueEntry = { code: string; label: string };
type Account = {
  account_id: string;
  number: string;
  name: string;
  operating_cost_type: string | null;
  operating_cost_type_label: string | null;
  suggested_operating_cost_type: string | null;
};

/** GAF-12: assign cost accounts to the BetrKV catalogue (human decision per account). */
export function CostTypeAccountsAdmin({ canManage }: { canManage: boolean }) {
  const t = useTranslations("BillingSetup.costTypes");
  const [ledgers, setLedgers] = useState<Ledger[]>([]);
  const [ledger, setLedger] = useState("");
  const [catalogue, setCatalogue] = useState<CatalogueEntry[]>([]);
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void bff<Ledger[]>("/api/bff/accounting/ledgers").then((r) => {
      if (r.ok) setLedgers(r.data ?? []);
    });
    void bff<{ items: CatalogueEntry[] }>("/api/bff/billing/operating-cost-types").then((r) => {
      if (r.ok) setCatalogue(r.data?.items ?? []);
    });
  }, []);
  async function load(id: string) {
    setLedger(id);
    setError(null);
    setAccounts(null);
    if (!id) return;
    const res = await bff<Account[]>(`/api/bff/billing/operating-cost-types/accounts?ledger_id=${encodeURIComponent(id)}`);
    if (res.ok) setAccounts(res.data ?? []);
    else setError(res.message);
  }
  async function map(accountId: string, code: string) {
    setError(null);
    const res = await bff<Account>(`/api/bff/billing/operating-cost-types/accounts/${accountId}`, {
      method: "PUT",
      body: JSON.stringify({ operating_cost_type: code || null }),
    });
    if (!res.ok) return setError(res.message);
    await load(ledger);
  }
  return (
    <section className="flex flex-col gap-3" data-testid="cost-type-accounts">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.notice}>{t("notice")}</p>
      <label className="flex flex-col gap-1 sm:max-w-sm">
        <span className={ui.label}>{t("ledger")}</span>
        <select className={ui.input} value={ledger} onChange={(e) => void load(e.target.value)}>
          <option value="">{t("choose")}</option>
          {ledgers.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </select>
      </label>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {accounts === null ? null : accounts.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("account")}</th>
                <th>{t("type")}</th>
                <th>{t("suggestion")}</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.account_id}>
                  <td>
                    {a.number} {a.name}
                  </td>
                  <td>
                    <select
                      className={ui.input}
                      aria-label={`${t("type")} ${a.number}`}
                      value={a.operating_cost_type ?? ""}
                      disabled={!canManage}
                      onChange={(e) => void map(a.account_id, e.target.value)}
                    >
                      <option value="">{t("none")}</option>
                      {catalogue.map((c) => (
                        <option key={c.code} value={c.code}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="text-muted">{a.suggested_operating_cost_type ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
