"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { bankAccountLabel, type BankAccountOption, type Transaction, type TransactionStatus } from "./bankTypes";
import { BookingDialog } from "./BookingDialog";
import { PayerIbanButton } from "./PayerIbanButton";
import { BulkConfirm } from "./BulkConfirm";

/** HOOK (plan M12 step S1): reopening an ignored transaction with a reason needs a new API
 *  operation (`ignore` is terminal today, `review` only accepts `needs_review`). Set the path
 *  builder once the backend package ships it; until then no reopen button is rendered. */
export const REOPEN_PATH: ((txId: string) => string) | null = null;

export const PAGE_SIZE = 50;
export const BULK_MAX = 200;

const STATUS_VARIANT: Record<string, StatusPillVariant> = {
  new: "gold",
  needs_review: "warning",
  proposed: "warning",
  booked: "success",
  ignored: "neutral",
  split: "neutral",
};
const STATUS_FILTERS: ("" | TransactionStatus)[] = ["", "new", "needs_review", "booked", "ignored"];
type Direction = "" | "in" | "out";

export type TransactionListProps = {
  canBook: boolean;
  canUpdate: boolean;
};

/** Daily bank work list (BK-2): filters by account, status, direction and period with offset
 *  pagination, booking dialog per transaction, duplicate clarification, ignore with reason,
 *  "Regel lernen" from a booked incoming transaction and bulk confirmation with preview. The
 *  direction filter is applied to the loaded page because the API has no direction parameter
 *  (docs/ASSUMPTIONS.md). */
export function TransactionList({ canBook, canUpdate }: TransactionListProps) {
  const t = useTranslations("Bank");
  const tl = useTranslations("Bank.list");
  const [accounts, setAccounts] = useState<BankAccountOption[]>([]);
  const [rows, setRows] = useState<Transaction[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [accountId, setAccountId] = useState("");
  const [status, setStatus] = useState<"" | TransactionStatus>("");
  const [direction, setDirection] = useState<Direction>("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [dialogTx, setDialogTx] = useState<Transaction | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [reviewReason, setReviewReason] = useState("");

  const load = useCallback(async () => {
    setError(null);
    const params = new URLSearchParams();
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String((page - 1) * PAGE_SIZE));
    if (accountId) params.set("bank_account_id", accountId);
    if (status) params.set("status", status);
    if (from) params.set("start", from);
    if (to) params.set("end", to);
    const res = await bff<Transaction[]>(`/api/bff/banking/transactions?${params.toString()}`);
    if (res.ok) setRows(res.data);
    else {
      setRows([]);
      setError(res.message);
    }
  }, [page, accountId, status, from, to]);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    (async () => {
      const res = await bff<BankAccountOption[]>("/api/bff/banking/accounts");
      if (res.ok) setAccounts(res.data);
    })();
  }, []);

  const legalEntityNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const a of accounts) if (a.legal_entity_name) map.set(a.legal_entity_id, a.legal_entity_name);
    return map;
  }, [accounts]);
  const accountLabels = useMemo(() => new Map(accounts.map((a) => [a.id, bankAccountLabel(a)])), [accounts]);
  const visible = useMemo(
    () =>
      (rows ?? []).filter((r) => {
        if (direction === "in") return Number(r.amount) > 0;
        if (direction === "out") return Number(r.amount) < 0;
        return true;
      }),
    [rows, direction],
  );
  const byId = useMemo(() => new Map((rows ?? []).map((r) => [r.id, r])), [rows]);
  const selectedRows = useMemo(() => visible.filter((r) => selected.has(r.id)), [visible, selected]);

  const resetPage = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setPage(1);
    setSelected(new Set());
  };

  const ignore = async (tx: Transaction) => {
    const reason = window.prompt(t("ignoreReason"));
    if (!reason || reason.trim().length < 3) return;
    setBusyId(tx.id);
    const res = await bff(`/api/bff/banking/transactions/${tx.id}/ignore`, {
      method: "POST",
      body: JSON.stringify({ decision: "ignore", reason: reason.trim() }),
    });
    setBusyId(null);
    if (res.ok) load();
    else setError(res.message);
  };
  const review = async (tx: Transaction, decision: "keep" | "ignore") => {
    if (reviewReason.trim().length < 3) return;
    setBusyId(tx.id);
    const res = await bff(`/api/bff/banking/transactions/${tx.id}/review`, {
      method: "POST",
      body: JSON.stringify({ decision, reason: reviewReason.trim() }),
    });
    setBusyId(null);
    if (res.ok) {
      setReviewId(null);
      setReviewReason("");
      load();
    } else setError(res.message);
  };
  const learn = async (tx: Transaction) => {
    setBusyId(tx.id);
    const res = await bff<{ id: string; name: string }>(`/api/bff/banking/transactions/${tx.id}/learn`, { method: "POST", body: "{}" });
    setBusyId(null);
    if (res.ok) setNotice(tl("learned", { name: res.data.name }));
    else setError(res.message);
  };
  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < BULK_MAX) next.add(id);
      return next;
    });
  const selectAllNew = () =>
    setSelected(new Set(visible.filter((r) => r.status === "new" && !r.transfer_pair_id).slice(0, BULK_MAX).map((r) => r.id)));

  const partnerBankAccountId = (tx: Transaction) => (tx.transfer_pair_id ? (byId.get(tx.transfer_pair_id)?.property_bank_account_id ?? null) : null);

  return (
    <section className="flex flex-col gap-3" data-testid="transaction-list">
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          load();
        }}
        aria-label={tl("filters")}
      >
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{tl("account")}</span>
          <select className={ui.input} value={accountId} onChange={(e) => resetPage(setAccountId)(e.target.value)}>
            <option value="">{tl("allAccounts")}</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {bankAccountLabel(a)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("status")}</span>
          <select className={ui.input} value={status} onChange={(e) => resetPage(setStatus)(e.target.value as "" | TransactionStatus)}>
            {STATUS_FILTERS.map((s) => (
              <option key={s} value={s}>
                {s === "" ? tl("allStatuses") : t(`txStatus.${s}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{tl("direction")}</span>
          <select className={ui.input} value={direction} onChange={(e) => resetPage(setDirection)(e.target.value as Direction)}>
            <option value="">{tl("bothDirections")}</option>
            <option value="in">{tl("incoming")}</option>
            <option value="out">{tl("outgoing")}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{tl("from")}</span>
          <input type="date" className={ui.input} value={from} onChange={(e) => resetPage(setFrom)(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{tl("to")}</span>
          <input type="date" className={ui.input} value={to} onChange={(e) => resetPage(setTo)(e.target.value)} />
        </label>
        <button type="submit" className={ui.button}>
          {tl("reload")}
        </button>
      </form>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className={ui.success} data-testid="list-notice">
          {notice}
        </p>
      ) : null}
      {canBook ? (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <button type="button" className={ui.buttonSm} onClick={selectAllNew}>
            {tl("selectNew")}
          </button>
          <button type="button" className={ui.buttonSm} onClick={() => setSelected(new Set())} disabled={selected.size === 0}>
            {tl("clearSelection")}
          </button>
          <button type="button" className={ui.primary} onClick={() => setBulkOpen(true)} disabled={selectedRows.length === 0}>
            {tl("bulk", { count: selectedRows.length })}
          </button>
        </div>
      ) : null}
      {rows === null ? (
        <p className="text-sm text-muted">{tl("loading")}</p>
      ) : visible.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                {canBook ? <th aria-label={tl("select")} /> : null}
                <th>{t("date")}</th>
                <th>{tl("account")}</th>
                <th>{t("counterpart")}</th>
                <th>{t("purpose")}</th>
                <th className="num">{t("amount")}</th>
                <th>{t("status")}</th>
                <th>{t("action")}</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((tx) => (
                <tr key={tx.id} className="align-top" data-testid="transaction-row">
                  {canBook ? (
                    <td>
                      {tx.status === "new" && !tx.transfer_pair_id ? (
                        <input type="checkbox" aria-label={tl("selectRow")} checked={selected.has(tx.id)} onChange={() => toggle(tx.id)} />
                      ) : null}
                    </td>
                  ) : null}
                  <td>{formatDate(tx.booking_date)}</td>
                  <td className="text-xs text-muted">{accountLabels.get(tx.property_bank_account_id) ?? ""}</td>
                  <td>
                    {tx.counterpart_name}
                    {tx.counterpart_iban_suffix ? <span className="ml-1 text-xs text-muted">…{tx.counterpart_iban_suffix}</span> : null}
                  </td>
                  <td>{tx.purpose}</td>
                  <td className="num">{formatEur(tx.amount)}</td>
                  <td>
                    <StatusPill variant={STATUS_VARIANT[tx.status] ?? "neutral"} label={t(`txStatus.${tx.status}`)} />
                    {tx.transfer_pair_id ? <span className={`ml-1 ${ui.badgeInfo}`}>{tl("transferPair")}</span> : null}
                  </td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      {tx.status === "new" && canBook ? (
                        <button type="button" className={ui.buttonSm} onClick={() => setDialogTx(tx)} disabled={busyId === tx.id}>
                          {tl("book")}
                        </button>
                      ) : null}
                      {tx.status === "new" && canUpdate ? (
                        <button type="button" className={ui.buttonSm} onClick={() => ignore(tx)} disabled={busyId === tx.id}>
                          {t("ignore")}
                        </button>
                      ) : null}
                      {tx.status === "needs_review" && canUpdate ? (
                        reviewId === tx.id ? (
                          <span className="flex flex-wrap items-center gap-1">
                            <input
                              aria-label={tl("reviewReason")}
                              className={ui.input}
                              placeholder={tl("reviewReason")}
                              value={reviewReason}
                              onChange={(e) => setReviewReason(e.target.value)}
                            />
                            <button type="button" className={ui.buttonSm} onClick={() => review(tx, "keep")} disabled={busyId === tx.id || reviewReason.trim().length < 3}>
                              {tl("reviewKeep")}
                            </button>
                            <button type="button" className={ui.buttonSm} onClick={() => review(tx, "ignore")} disabled={busyId === tx.id || reviewReason.trim().length < 3}>
                              {tl("reviewIgnore")}
                            </button>
                            <button type="button" className={ui.buttonSm} onClick={() => setReviewId(null)}>
                              {tl("cancel")}
                            </button>
                          </span>
                        ) : (
                          <button type="button" className={ui.buttonSm} onClick={() => setReviewId(tx.id)}>
                            {tl("review")}
                          </button>
                        )
                      ) : null}
                      {tx.status === "booked" && canBook && Number(tx.amount) > 0 ? (
                        <button type="button" className={ui.buttonSm} onClick={() => learn(tx)} disabled={busyId === tx.id}>
                          {tl("learn")}
                        </button>
                      ) : null}
                      {tx.status === "booked" && canUpdate && Number(tx.amount) > 0 ? <PayerIbanButton txId={tx.id} /> : null}
                      {tx.status === "ignored" && canUpdate && REOPEN_PATH ? (
                        <button type="button" className={ui.buttonSm} disabled>
                          {tl("reopen")}
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <nav className="flex items-center gap-3 text-sm" aria-label={tl("pagination")}>
        <span className="text-muted">{tl("pageInfo", { page, count: visible.length })}</span>
        <span className="ml-auto" />
        <button type="button" className={ui.button} disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
          {tl("prev")}
        </button>
        <button type="button" className={ui.button} disabled={(rows?.length ?? 0) < PAGE_SIZE} onClick={() => setPage((p) => p + 1)}>
          {tl("next")}
        </button>
      </nav>
      <p className="text-xs text-muted">
        {tl("rulesHint")}{" "}
        <Link href="/bank/regeln" className="underline">
          {tl("rulesLink")}
        </Link>
      </p>
      {dialogTx ? (
        <BookingDialog
          tx={dialogTx}
          partnerBankAccountId={partnerBankAccountId(dialogTx)}
          onClose={() => setDialogTx(null)}
          onBooked={(result) => {
            setDialogTx(null);
            setNotice(tl("booked", { number: result.number }));
            load();
          }}
        />
      ) : null}
      {bulkOpen ? (
        <BulkConfirm
          transactions={selectedRows}
          legalEntityNames={legalEntityNames}
          onClose={() => setBulkOpen(false)}
          onDone={() => {
            setBulkOpen(false);
            setSelected(new Set());
            load();
          }}
        />
      ) : null}
    </section>
  );
}
