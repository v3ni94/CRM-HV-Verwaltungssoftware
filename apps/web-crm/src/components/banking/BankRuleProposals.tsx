"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { parseAmount } from "./bankTypes";

export type RuleProposal = {
  id: string;
  legal_entity_id: string;
  pattern_key: string;
  status: string;
  direction: "credit" | "debit" | string;
  case_kind: string;
  has_iban_key: boolean;
  creditor_id: string | null;
  account_number: string;
  account_id: string | null;
  action_kind: string;
  amount_min: string;
  amount_max: string;
  purpose_tokens: string[];
  recurring: boolean;
  threshold: number;
  evidence: { decision_ids?: string[]; transaction_ids?: string[]; first_at?: string; last_at?: string; amounts?: string[] };
  evidence_count: string;
  reason: string | null;
  rule_id: string | null;
  created_at: string;
};

export type BankRuleProposalsProps = { canApprove: boolean; onAccepted?: () => void };

/** Gelernte Regelvorschläge (Regel M12-06): aus wiederholten gleichen Entscheidungen von Personen;
 *  Annahme erzeugt eine Bankregel im Zustand vorgeschlagen (verengen erlaubt, erweitern nicht),
 *  Ablehnung mit Grund. Ein Vorschlag bucht nichts und aktiviert nichts. */
export function BankRuleProposals({ canApprove, onAccepted }: BankRuleProposalsProps) {
  const t = useTranslations("Bank.ruleProposals");
  const [rows, setRows] = useState<RuleProposal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [amountMax, setAmountMax] = useState("");
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const load = useCallback(async () => {
    const res = await bff<RuleProposal[]>("/api/bff/banking/rule-proposals?status=proposed");
    if (res.ok) setRows(res.data);
    else {
      setRows([]);
      setError(res.message);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const accept = async (row: RuleProposal) => {
    setError(null);
    const body: Record<string, unknown> = {};
    if (amountMax.trim()) {
      const cap = parseAmount(amountMax);
      if (cap === null) {
        setError(t("invalidAmount", { value: amountMax.trim() }));
        return;
      }
      body.amount_max = cap;
    }
    setBusy(row.id);
    const res = await bff<{ id: string; name: string }>(`/api/bff/banking/rule-proposals/${row.id}/accept`, { method: "POST", body: JSON.stringify(body) });
    setBusy(null);
    if (res.ok) {
      setNotice(t("accepted", { name: res.data.name }));
      setEditing(null);
      setAmountMax("");
      load();
      onAccepted?.();
    } else setError(res.message);
  };

  const reject = async (row: RuleProposal) => {
    if (rejectReason.trim().length < 3) return;
    setBusy(row.id);
    setError(null);
    const res = await bff<RuleProposal>(`/api/bff/banking/rule-proposals/${row.id}/reject`, { method: "POST", body: JSON.stringify({ reason: rejectReason.trim() }) });
    setBusy(null);
    if (res.ok) {
      setRejecting(null);
      setRejectReason("");
      load();
    } else setError(res.message);
  };

  return (
    <section className="flex flex-col gap-3" data-testid="bank-rule-proposals">
      <h2 className={ui.h3}>{t("title")}</h2>
      <p className={ui.help}>{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {notice ? <p className={ui.success}>{notice}</p> : null}
      {rows === null ? <p className="text-sm text-muted">{t("loading")}</p> : null}
      {rows && rows.length === 0 ? <EmptyState title={t("empty")} /> : null}
      {rows && rows.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {rows.map((row) => (
            <li key={row.id} className={`${ui.card} flex flex-col gap-1 text-sm`} data-testid="rule-proposal">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">
                  {t("account", { number: row.account_number })} · {row.direction === "credit" ? t("credit") : t("debit")}
                </span>
                {row.recurring ? <span className={ui.badge}>{t("recurring")}</span> : null}
                <span className="text-muted">{t("evidence", { count: row.evidence_count, threshold: row.threshold })}</span>
              </div>
              <p className="text-muted">
                {row.has_iban_key ? t("keyIban") : t("keyCreditor", { id: row.creditor_id ?? "" })}; {t("band", { min: formatEur(row.amount_min), max: formatEur(row.amount_max) })}
                {row.purpose_tokens.length > 0 ? `; ${t("tokens", { tokens: row.purpose_tokens.join(", ") })}` : ""}
              </p>
              <p className="text-muted">
                {row.evidence.first_at ? t("period", { from: formatDate(row.evidence.first_at), to: formatDate(row.evidence.last_at ?? row.evidence.first_at) }) : null}
              </p>
              {canApprove ? (
                <div className="flex flex-col gap-2">
                  <div className={ui.formActions}>
                    <button type="button" className={ui.primary} disabled={busy === row.id} onClick={() => setEditing(editing === row.id ? null : row.id)}>
                      {t("accept")}
                    </button>
                    <button type="button" className={ui.secondary} disabled={busy === row.id} onClick={() => setRejecting(rejecting === row.id ? null : row.id)}>
                      {t("reject")}
                    </button>
                  </div>
                  {editing === row.id ? (
                    <form
                      className="flex flex-col gap-2"
                      data-testid="accept-form"
                      onSubmit={(e) => {
                        e.preventDefault();
                        accept(row);
                      }}
                    >
                      <label className="flex flex-col gap-1">
                        <span className={ui.label}>{t("narrowMax", { max: formatEur(row.amount_max) })}</span>
                        <input className={ui.input} inputMode="decimal" value={amountMax} onChange={(e) => setAmountMax(e.target.value)} />
                      </label>
                      <p className={ui.help}>{t("narrowHint")}</p>
                      <button type="submit" className={ui.primary} disabled={busy === row.id}>
                        {t("acceptConfirm")}
                      </button>
                    </form>
                  ) : null}
                  {rejecting === row.id ? (
                    <form
                      className="flex flex-col gap-2"
                      data-testid="reject-form"
                      onSubmit={(e) => {
                        e.preventDefault();
                        reject(row);
                      }}
                    >
                      <label className="flex flex-col gap-1">
                        <span className={ui.label}>{t("rejectReason")}</span>
                        <input className={ui.input} required minLength={3} maxLength={2000} value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
                      </label>
                      <button type="submit" className={ui.secondary} disabled={busy === row.id || rejectReason.trim().length < 3}>
                        {t("rejectConfirm")}
                      </button>
                    </form>
                  ) : null}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
