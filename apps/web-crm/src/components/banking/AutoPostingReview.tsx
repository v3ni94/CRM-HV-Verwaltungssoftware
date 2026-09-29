"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { accountLabel, type LedgerAccount } from "./bankTypes";

export type ReviewItem = {
  id: string;
  posting_decision_id: string;
  bank_transaction_id: string;
  legal_entity_id: string;
  journal_entry_id: string | null;
  journal_number: string | null;
  ledger_id: string | null;
  rule_id: string | null;
  case_kind: string;
  kind: "daily" | "sample" | "return" | string;
  due_on: string;
  overdue: boolean;
  status: string;
  note: string | null;
  booking_date: string | null;
  amount: string | null;
  counterpart_name: string | null;
  purpose: string | null;
  final: { settlements?: { open_item_id: string; amount: string }[]; counter_account_number?: string | null } | null;
  verifier_fingerprint: string | null;
  reversed: boolean;
  return_transaction_id: string | null;
};

const REASON_CODES = ["automation_error", "wrong_assignment", "wrong_amount", "wrong_date", "duplicate", "other"] as const;

export type AutoPostingReviewProps = { canReview: boolean; canBook: boolean };

/** Nachkontrolle automatischer Buchungen (Regel M12-05, 7.4 Nr. 4): offene Posten mit Fälligkeit,
 *  Bestätigung mit In Ordnung (Recht accounting:review) oder Korrigieren: Storno mit Grundcode plus
 *  Neubuchung gegen ein Gegenkonto in einem Schritt (B03); die gebuchte Buchung wird nie geändert. */
export function AutoPostingReview({ canReview, canBook }: AutoPostingReviewProps) {
  const t = useTranslations("Bank.review");
  const [rows, setRows] = useState<ReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [correcting, setCorrecting] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<LedgerAccount[]>([]);
  const [account, setAccount] = useState("");
  const [reason, setReason] = useState("");
  const [code, setCode] = useState<(typeof REASON_CODES)[number]>("automation_error");

  const load = useCallback(async () => {
    const res = await bff<ReviewItem[]>("/api/bff/banking/auto-posting/reviews");
    if (res.ok) setRows(res.data);
    else {
      setRows([]);
      setError(res.message);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const openCorrection = async (item: ReviewItem) => {
    setCorrecting(correcting === item.id ? null : item.id);
    setAccount("");
    if (item.ledger_id) {
      const res = await bff<LedgerAccount[]>(`/api/bff/accounting/ledgers/${item.ledger_id}/accounts`);
      if (res.ok) setAccounts(res.data.filter((a) => a.active && !a.is_system && a.property_bank_account_id === null));
    }
  };

  const ok = async (item: ReviewItem) => {
    setBusy(item.id);
    setError(null);
    const res = await bff<ReviewItem>(`/api/bff/banking/auto-posting/reviews/${item.id}`, { method: "POST", body: JSON.stringify({ outcome: "ok" }) });
    setBusy(null);
    if (res.ok) {
      setNotice(t("confirmed", { number: item.journal_number ?? "" }));
      load();
    } else setError(res.message);
  };

  const correct = async (item: ReviewItem) => {
    if (!account || reason.trim().length < 3) return;
    setBusy(item.id);
    setError(null);
    const res = await bff<{ reversal_number: string; number: string }>(`/api/bff/banking/transactions/${item.bank_transaction_id}/correct`, {
      method: "POST",
      body: JSON.stringify({ reason: reason.trim(), reason_code: code, settlements: [], counter_account_id: account }),
    });
    setBusy(null);
    if (res.ok) {
      setNotice(t("corrected", { reversal: res.data.reversal_number, number: res.data.number }));
      setCorrecting(null);
      setReason("");
      load();
    } else setError(res.message);
  };

  return (
    <section className="flex flex-col gap-3" data-testid="auto-posting-review">
      <p className={ui.notice}>{t("intro")}</p>
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
          {rows.map((item) => (
            <li key={item.id} className={`${ui.card} flex flex-col gap-1 text-sm`} data-testid="review-item">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{item.counterpart_name ?? item.bank_transaction_id}</span>
                <span className="tabular-nums">{item.amount ? formatEur(item.amount) : ""}</span>
                <span className="text-muted">{formatDate(item.booking_date)}</span>
                <StatusPill label={item.overdue ? t("overdue") : t("dueOn", { date: formatDate(item.due_on) })} variant={item.overdue ? "danger" : "gold"} />
                <span className={ui.badge}>{t(`kind_${item.kind}` as "kind_daily")}</span>
                <span className={ui.badge}>{item.case_kind}</span>
              </div>
              <p className="text-muted">
                {item.purpose} · {t("entry", { number: item.journal_number ?? "" })}
                {item.final?.counter_account_number ? ` · ${t("counter", { number: item.final.counter_account_number })}` : ""}
              </p>
              {item.kind === "return" ? <p className={ui.help}>{t("returnHint")}</p> : null}
              <div className={ui.formActions}>
                {canReview ? (
                  <button type="button" className={ui.primary} disabled={busy === item.id || item.reversed} onClick={() => ok(item)}>
                    {t("ok")}
                  </button>
                ) : null}
                {canBook && !item.reversed ? (
                  <button type="button" className={ui.secondary} disabled={busy === item.id} onClick={() => openCorrection(item)}>
                    {t("correct")}
                  </button>
                ) : null}
              </div>
              {correcting === item.id ? (
                <form
                  className="grid gap-2 sm:grid-cols-2"
                  data-testid="correct-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    correct(item);
                  }}
                >
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("reasonCode")}</span>
                    <select className={ui.input} value={code} onChange={(e) => setCode(e.target.value as (typeof REASON_CODES)[number])}>
                      {REASON_CODES.map((c) => (
                        <option key={c} value={c}>
                          {t(`code_${c}` as "code_other")}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("counterAccount")}</span>
                    <select className={ui.input} required value={account} onChange={(e) => setAccount(e.target.value)}>
                      <option value="">{t("chooseAccount")}</option>
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {accountLabel(a)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1 sm:col-span-2">
                    <span className={ui.label}>{t("reason")}</span>
                    <input className={ui.input} required minLength={3} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
                  </label>
                  <p className={`${ui.help} sm:col-span-2`}>{t("correctHint")}</p>
                  <div className={`${ui.formActions} sm:col-span-2`}>
                    <button type="submit" className={ui.primary} disabled={busy === item.id || !account || reason.trim().length < 3}>
                      {t("correctConfirm")}
                    </button>
                    <button type="button" className={ui.secondary} onClick={() => setCorrecting(null)}>
                      {t("cancel")}
                    </button>
                  </div>
                </form>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
