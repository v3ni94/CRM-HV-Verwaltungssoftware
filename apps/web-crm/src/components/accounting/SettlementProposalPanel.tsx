"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type AccountOption = { id: string; number: string; name?: string };

type Allocation = {
  open_item_id: string;
  amount: string;
  remaining_before: string;
  reason: string;
  rank: number;
  due_date: string | null;
  claim_class: string;
};
type Proposal = {
  rule: string;
  rule_version: string;
  note: string;
  requires_confirmation: boolean;
  basis: string;
  amount: string;
  as_of: string;
  allocations: Allocation[];
  unallocated: string;
  fingerprint: string;
};

/** Settlement proposal in the statutory order (M10-03, D39): the platform proposes, a staff
 *  member confirms. The confirmation creates a draft entry; nothing is posted here. */
export function SettlementProposalPanel({
  ledgerId,
  debtors,
  bankAccounts,
  today,
}: {
  ledgerId: string;
  debtors: AccountOption[];
  bankAccounts: AccountOption[];
  today: string;
}) {
  const t = useTranslations("Receivables.settlement");
  const router = useRouter();
  const [accountId, setAccountId] = useState(debtors[0]?.id ?? "");
  const [bankId, setBankId] = useState(bankAccounts[0]?.id ?? "");
  const [amount, setAmount] = useState("");
  const [purpose, setPurpose] = useState("");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const body = () => ({ account_id: accountId, amount, as_of: today, purpose: purpose || null });
  const base = `/api/bff/accounting/ledgers/${ledgerId}/open-items/settlement-proposal`;

  const propose = async () => {
    setBusy(true);
    setError(null);
    setDone(null);
    const res = await bff<Proposal>(base, { method: "POST", body: JSON.stringify(body()) });
    setBusy(false);
    if (res.ok) setProposal(res.data);
    else setError(res.message);
  };
  const confirm = async () => {
    if (!proposal) return;
    if (!window.confirm(t("confirmQuestion", { amount: formatEur(proposal.amount) }))) return;
    setBusy(true);
    setError(null);
    const res = await bff<{ id: string }>(`${base}/confirm`, {
      method: "POST",
      body: JSON.stringify({
        ...body(),
        fingerprint: proposal.fingerprint,
        bank_account_id: bankId,
        booking_date: today,
      }),
    });
    setBusy(false);
    if (res.ok) {
      setDone(res.data.id);
      setProposal(null);
      router.refresh();
    } else setError(res.message);
  };

  if (debtors.length === 0) return null;
  return (
    <div className={`${ui.card} flex flex-col gap-3`}>
      <h3 className={ui.h2}>{t("title")}</h3>
      <p className={ui.notice}>{t("intro")}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className={ui.label}>
          {t("debtor")}
          <select className={ui.input} value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            {debtors.map((d) => (
              <option key={d.id} value={d.id}>
                {d.number} {d.name ?? ""}
              </option>
            ))}
          </select>
        </label>
        <label className={ui.label}>
          {t("bank")}
          <select className={ui.input} value={bankId} onChange={(e) => setBankId(e.target.value)}>
            {bankAccounts.map((b) => (
              <option key={b.id} value={b.id}>
                {b.number} {b.name ?? ""}
              </option>
            ))}
          </select>
        </label>
        <label className={ui.label}>
          {t("amount")}
          <input className={ui.input} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
        </label>
        <label className={ui.label}>
          {t("purpose")}
          <input className={ui.input} value={purpose} onChange={(e) => setPurpose(e.target.value)} />
        </label>
      </div>
      <div className={ui.formActions}>
        <button type="button" className={ui.button} onClick={propose} disabled={busy || !amount || !accountId}>
          {t("propose")}
        </button>
      </div>
      {error ? (
        <span role="alert" className={ui.error}>
          {error}
        </span>
      ) : null}
      {done ? <p className={ui.success}>{t("created")}</p> : null}
      {proposal ? (
        <div className="flex flex-col gap-2" data-testid="settlement-proposal">
          <p className={ui.badgeWarning}>{proposal.note}</p>
          <p className="text-xs text-muted">
            {t("basis", { basis: t(`bases.${proposal.basis}`) })} · {t("rule", { rule: proposal.rule, version: proposal.rule_version })}
          </p>
          {proposal.allocations.length === 0 ? (
            <p className="text-sm text-muted">{t("empty")}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="mhvp-table">
                <thead>
                  <tr>
                    <th>{t("rank")}</th>
                    <th>{t("due")}</th>
                    <th>{t("claimClass")}</th>
                    <th className="num">{t("open")}</th>
                    <th className="num">{t("allocated")}</th>
                    <th>{t("reason")}</th>
                  </tr>
                </thead>
                <tbody>
                  {proposal.allocations.map((a) => (
                    <tr key={a.open_item_id}>
                      <td>{a.rank}</td>
                      <td>{formatDate(a.due_date)}</td>
                      <td>{t(`classes.${a.claim_class}`)}</td>
                      <td className="num">{formatEur(a.remaining_before)}</td>
                      <td className="num">{formatEur(a.amount)}</td>
                      <td>{a.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {Number(proposal.unallocated) > 0 ? (
            <p className="text-sm text-muted" data-testid="settlement-unallocated">
              {t("unallocated", { amount: formatEur(proposal.unallocated) })}
            </p>
          ) : null}
          <div className={ui.formActions}>
            <button
              type="button"
              className={ui.primary}
              onClick={confirm}
              disabled={busy || !bankId || proposal.allocations.length === 0}
            >
              {t("confirm")}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
