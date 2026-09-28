"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { fromCents, toCents, type Proposal, type Proposals, type Split, type Transaction } from "./bankTypes";

type Item = { transaction_id: string; settlements: { open_item_id: string; amount: string }[] };
type PreviewOut = {
  preview: true;
  count: number;
  total: string;
  legal_entities: string[];
  exceptions: string[];
  allocations: Record<string, { open_item_id: string; amount: string; allocation_reason: string }[]>;
};
type ResultOut = {
  preview: false;
  count: number;
  total: string;
  legal_entities: string[];
  exceptions: string[];
  results: { transaction_id: string; ok: boolean; journal_entry_id?: string; error?: string }[];
};

/** Only deterministically verified proposals qualify for the bulk path (plan M12, level L1):
 *  an unambiguous full settlement or a hit of an approved or active bank rule with splits.
 *  History and AI proposals are never pre-selected. */
export function verifiedSplits(proposals: Proposals): Split[] | null {
  const hit = proposals.stage1.find(
    (p: Proposal) => (p.unambiguous === true || p.source === "rule") && p.splits && p.splits.length > 0,
  );
  return hit?.splits ?? null;
}

export type BulkConfirmProps = {
  transactions: Transaction[];
  legalEntityNames: Map<string, string>;
  onClose: () => void;
  onDone: () => void;
};

/** Bulk confirmation with preview (7.4, plan M12 S2): loads the stage 1 proposals of every
 *  selected transaction, takes only verified splits, shows count, sums per legal entity and
 *  exceptions from `POST /banking/bulk-confirm?preview`, then books on explicit confirmation
 *  (each transaction completely or not at all; the API decides per item). The API counts and
 *  sums every submitted item and lists exceptions (already booked, ignored, transfer pair)
 *  separately; the preview here shows only what will be booked, and only that is sent. */
export function BulkConfirm({ transactions, legalEntityNames, onClose, onDone }: BulkConfirmProps) {
  const t = useTranslations("Bank.bulk");
  const [items, setItems] = useState<Item[] | null>(null);
  const [skipped, setSkipped] = useState<Transaction[]>([]);
  const [preview, setPreview] = useState<PreviewOut | null>(null);
  const [result, setResult] = useState<ResultOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const built: Item[] = [];
      const none: Transaction[] = [];
      for (const tx of transactions) {
        const res = await bff<Proposals>(`/api/bff/banking/transactions/${tx.id}/posting-proposals`);
        if (cancelled) return;
        const splits = res.ok ? verifiedSplits(res.data) : null;
        if (splits) built.push({ transaction_id: tx.id, settlements: splits.map((s) => ({ open_item_id: s.open_item_id, amount: s.amount })) });
        else none.push(tx);
      }
      setItems(built);
      setSkipped(none);
      if (built.length === 0) return;
      const pv = await bff<PreviewOut>("/api/bff/banking/bulk-confirm", {
        method: "POST",
        body: JSON.stringify({ items: built, preview: true }),
      });
      if (cancelled) return;
      if (pv.ok) setPreview(pv.data);
      else setError(pv.message);
    })();
    return () => {
      cancelled = true;
    };
  }, [transactions]);

  const byId = new Map(transactions.map((tx) => [tx.id, tx]));
  const excepted = new Set(preview?.exceptions ?? []);
  const bookable = preview ? (items ?? []).filter((item) => !excepted.has(item.transaction_id)) : [];
  const bookableCents = bookable.reduce((sum, item) => sum + Math.abs(toCents(byId.get(item.transaction_id)?.amount)), 0);
  const sumsPerEntity = () => {
    const sums = new Map<string, number>();
    for (const item of bookable) {
      const tx = byId.get(item.transaction_id);
      if (!tx) continue;
      sums.set(tx.legal_entity_id, (sums.get(tx.legal_entity_id) ?? 0) + Math.abs(toCents(tx.amount)));
    }
    return [...sums.entries()];
  };

  const confirm = async () => {
    if (bookable.length === 0) return;
    setBusy(true);
    setError(null);
    const res = await bff<ResultOut>("/api/bff/banking/bulk-confirm", {
      method: "POST",
      body: JSON.stringify({ items: bookable, preview: false }),
    });
    setBusy(false);
    if (res.ok) setResult(res.data);
    else setError(res.message);
  };

  return (
    <div className={`fixed inset-0 z-40 flex items-start justify-center overflow-y-auto p-4 ${ui.scrim}`} data-testid="bulk-confirm">
      <div role="dialog" aria-modal="true" aria-labelledby="bulk-title" className={`${ui.popover} my-6 w-full max-w-2xl p-4 sm:p-6`}>
        <h2 id="bulk-title" className={ui.h2}>
          {t("title")}
        </h2>
        <p className="text-sm text-muted">{t("intro")}</p>
        {error ? (
          <p role="alert" className={`${ui.alert} mt-3`}>
            {error}
          </p>
        ) : null}
        {items === null ? <p className="mt-3 text-sm text-muted">{t("loading")}</p> : null}
        {items !== null && result === null ? (
          <div className="mt-3 flex flex-col gap-2 text-sm">
            <dl className="grid grid-cols-2 gap-x-3">
              <dt className="text-muted">{t("selected")}</dt>
              <dd className="text-right tabular-nums">{transactions.length}</dd>
              <dt className="text-muted">{t("verified")}</dt>
              <dd className="text-right tabular-nums" data-testid="bulk-count">
                {bookable.length}
              </dd>
              <dt className="text-muted">{t("total")}</dt>
              <dd className="text-right tabular-nums" data-testid="bulk-total">
                {preview ? formatEur(fromCents(bookableCents)) : ""}
              </dd>
            </dl>
            <h3 className={ui.h3}>{t("perEntity")}</h3>
            <ul className="flex flex-col gap-1">
              {sumsPerEntity().map(([entityId, cents]) => (
                <li key={entityId} className="flex justify-between">
                  <span>{legalEntityNames.get(entityId) ?? entityId}</span>
                  <span className="tabular-nums">{formatEur(fromCents(cents))}</span>
                </li>
              ))}
            </ul>
            <h3 className={ui.h3}>{t("exceptions")}</h3>
            {skipped.length === 0 && (preview?.exceptions.length ?? 0) === 0 ? (
              <p className="text-muted">{t("noExceptions")}</p>
            ) : (
              <ul className="list-disc pl-5" data-testid="bulk-exceptions">
                {skipped.map((tx) => (
                  <li key={tx.id}>
                    {tx.counterpart_name ?? tx.id} {formatEur(tx.amount)}: {t("noVerifiedProposal")}
                  </li>
                ))}
                {(preview?.exceptions ?? []).map((id) => (
                  <li key={id}>
                    {byId.get(id)?.counterpart_name ?? id}: {t("apiException")}
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs text-muted">{t("note")}</p>
            <div className={ui.formActions}>
              <button type="button" className={ui.primary} onClick={confirm} disabled={busy || !preview || bookable.length === 0}>
                {t("confirm", { count: bookable.length })}
              </button>
              <button type="button" className={ui.secondary} onClick={onClose} disabled={busy}>
                {t("cancel")}
              </button>
            </div>
          </div>
        ) : null}
        {result ? (
          <div className="mt-3 flex flex-col gap-2 text-sm">
            <p data-testid="bulk-result">
              {t("result", { ok: result.results.filter((r) => r.ok).length, failed: result.results.filter((r) => !r.ok).length })}
            </p>
            <ul className="list-disc pl-5">
              {result.results
                .filter((r) => !r.ok)
                .map((r) => (
                  <li key={r.transaction_id}>
                    {byId.get(r.transaction_id)?.counterpart_name ?? r.transaction_id}: {r.error}
                  </li>
                ))}
            </ul>
            <div className={ui.formActions}>
              <button type="button" className={ui.primary} onClick={onDone}>
                {t("close")}
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
