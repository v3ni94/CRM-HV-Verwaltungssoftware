"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Line = { account_number?: string; account_name?: string; amount: string };
type Finding = { code: string; level: string; message: string };
type Results = {
  income: { rent: string; advances: string; other: string; total: string; lines: Line[] };
  expenses: { lines: Line[]; total: string };
  admin_fee: { net: string; vat: string; gross: string; basis: string };
  payouts: { lines: Line[]; total: string };
  open_receivables: { total: string; items: { contract_id: string | null; component: string | null; due_date: string | null; remaining: string }[] };
  open_payables: { total: string };
  deposits: { held: string; bank_segregated: string; difference: string; items: { contract_number: string; kind: string; balance: string }[] };
  liquidity: { bank_total: string; deposits_held: string; open_payables: string; free: string };
  operating_result: { result: string };
  sev_reconciliation?: {
    hoa_cost_share: string;
    hausgeld_resolved: string;
    hausgeld_paid: string;
    hausgeld_open: string;
    hoa_result: string;
    tenant_allocable_costs: string;
    vacancy_owner_share: string;
    owner_burden: string;
    hoa_statement: { statement_id: string; year: number; version: number } | null;
  };
};
export type OwnerStatement = {
  id: string;
  kind: "rental_owner" | "sev_owner";
  ledger_id: string;
  period_from: string;
  period_to: string;
  status: "draft" | "calculated" | "internally_approved";
  snapshot_hash: string | null;
  results?: Results | null;
  findings?: Finding[];
};

const BASE = "/api/bff/billing/owner-statements";

export function OwnerStatementPanel({ ledgers }: { ledgers: { id: string; name: string }[] }) {
  const t = useTranslations("OwnerStatements");
  const year = new Date().getFullYear() - 1;
  const [ledger, setLedger] = useState(ledgers[0]?.id ?? "");
  const [from, setFrom] = useState(`${year}-01-01`);
  const [to, setTo] = useState(`${year}-12-31`);
  const [list, setList] = useState<OwnerStatement[]>([]);
  const [selected, setSelected] = useState<OwnerStatement | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<OwnerStatement[]>(BASE);
    if (res.ok) setList(res.data);
    else setError(res.message);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const open = async (id: string) => {
    setError(null);
    const res = await bff<OwnerStatement>(`${BASE}/${id}`);
    if (res.ok) setSelected(res.data);
    else setError(res.message);
  };
  const create = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<OwnerStatement>(BASE, {
      method: "POST",
      body: JSON.stringify({ ledger_id: ledger, period_from: from, period_to: to }),
    });
    setBusy(false);
    if (res.ok) {
      setSelected(res.data);
      await load();
    } else setError(res.message);
  };
  const calculate = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    const res = await bff<OwnerStatement>(`${BASE}/${selected.id}/calculate`, { method: "POST" });
    setBusy(false);
    if (res.ok) {
      setSelected(res.data);
      await load();
    } else setError(res.message);
  };
  const ledgerName = (id: string) => ledgers.find((l) => l.id === id)?.name ?? id;

  return (
    <div className={ui.sectionGap}>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("ledger")}</span>
          <select className={ui.input} value={ledger} onChange={(e) => setLedger(e.target.value)}>
            {ledgers.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
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
        <button type="button" className={ui.primary} onClick={create} disabled={busy || !ledger}>
          {t("create")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {list.length === 0 ? (
        <p className={ui.help}>{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("ledger")}</th>
                <th>{t("kind")}</th>
                <th>{t("period")}</th>
                <th>{t("statusLabel")}</th>
              </tr>
            </thead>
            <tbody>
              {list.map((s) => (
                <tr key={s.id} className={s.id === selected?.id ? "bg-surface" : undefined}>
                  <td>
                    <button type="button" className="font-medium hover:underline" onClick={() => open(s.id)}>
                      {ledgerName(s.ledger_id)}
                    </button>
                  </td>
                  <td>{t(`kinds.${s.kind}`)}</td>
                  <td>
                    {formatDate(s.period_from)} {t("until")} {formatDate(s.period_to)}
                  </td>
                  <td>{t(`status.${s.status}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selected ? (
        <section className={ui.card} aria-label={t("detail")}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">
              {t("detail")}: {ledgerName(selected.ledger_id)}, {formatDate(selected.period_from)} {t("until")}{" "}
              {formatDate(selected.period_to)}
            </h2>
            <span className={ui.badge}>{t(`status.${selected.status}`)}</span>
          </div>
          {selected.status !== "internally_approved" ? (
            <button type="button" className={`${ui.secondary} mt-3`} onClick={calculate} disabled={busy}>
              {t("calculate")}
            </button>
          ) : null}
          {selected.results ? <Blocks results={selected.results} findings={selected.findings ?? []} /> : <p className={`${ui.help} mt-3`}>{t("notCalculated")}</p>}
          <p className={`${ui.notice} mt-4`}>{t("gateNotice")}</p>
        </section>
      ) : null}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <tr>
      <td>{label}</td>
      <td className="num">{formatEur(value)}</td>
    </tr>
  );
}

export function Blocks({ results, findings }: { results: Results; findings: Finding[] }) {
  const t = useTranslations("OwnerStatements");
  const sev = results.sev_reconciliation;
  return (
    <div className="mt-4 grid gap-4 md:grid-cols-2">
      <Block title={t("blocks.income")}>
        <Row label={t("income.rent")} value={results.income.rent} />
        <Row label={t("income.advances")} value={results.income.advances} />
        <Row label={t("income.other")} value={results.income.other} />
        <Row label={t("total")} value={results.income.total} />
      </Block>
      <Block title={t("blocks.expenses")}>
        {results.expenses.lines.map((l) => (
          <Row key={l.account_number} label={`${l.account_number} ${l.account_name ?? ""}`} value={l.amount} />
        ))}
        <Row label={t("total")} value={results.expenses.total} />
      </Block>
      <Block title={t("blocks.adminFee")}>
        <Row label={t("fee.net")} value={results.admin_fee.net} />
        <Row label={t("fee.vat")} value={results.admin_fee.vat} />
        <Row label={t("fee.gross")} value={results.admin_fee.gross} />
      </Block>
      <Block title={t("blocks.payouts")}>
        <Row label={t("total")} value={results.payouts.total} />
      </Block>
      <Block title={t("blocks.receivables")}>
        <Row label={t("total")} value={results.open_receivables.total} />
      </Block>
      <Block title={t("blocks.deposits")}>
        <Row label={t("deposits.held")} value={results.deposits.held} />
        <Row label={t("deposits.bank")} value={results.deposits.bank_segregated} />
      </Block>
      <Block title={t("blocks.liquidity")}>
        <Row label={t("liquidity.bank")} value={results.liquidity.bank_total} />
        <Row label={t("liquidity.deposits")} value={results.liquidity.deposits_held} />
        <Row label={t("liquidity.payables")} value={results.liquidity.open_payables} />
        <Row label={t("liquidity.free")} value={results.liquidity.free} />
      </Block>
      <Block title={t("blocks.result")}>
        <Row label={t("operatingResult")} value={results.operating_result.result} />
      </Block>
      {sev ? (
        <Block title={t("blocks.sev")}>
          <Row label={t("sev.hoaCostShare")} value={sev.hoa_cost_share} />
          <Row label={t("sev.hausgeldResolved")} value={sev.hausgeld_resolved} />
          <Row label={t("sev.hausgeldPaid")} value={sev.hausgeld_paid} />
          <Row label={t("sev.hoaResult")} value={sev.hoa_result} />
          <Row label={t("sev.tenantCosts")} value={sev.tenant_allocable_costs} />
          <Row label={t("sev.ownerBurden")} value={sev.owner_burden} />
        </Block>
      ) : null}
      <div className="md:col-span-2">
        <h3 className={ui.subtitle}>{t("findings")}</h3>
        {findings.length === 0 ? (
          <p className={ui.help}>{t("noFindings")}</p>
        ) : (
          <ul className="mt-1 flex flex-col gap-1 text-sm">
            {findings.map((f) => (
              <li key={f.code}>
                <span className={f.level === "error" ? ui.badgeDanger : f.level === "warning" ? ui.badgeWarning : ui.badge}>{f.code}</span> {f.message}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className={ui.subtitle}>{title}</h3>
      <table className="mhvp-table mt-1">
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
