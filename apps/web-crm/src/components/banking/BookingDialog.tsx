"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { AiPostingPanel } from "./AiPostingPanel";

import {
  accountLabel,
  fromCents,
  isContraAccountCandidate,
  isPartnerBankAccountCandidate,
  parseAmount,
  toCents,
  type AiProposal,
  type LedgerAccount,
  type OpenItem,
  type Proposal,
  type Proposals,
  type Split,
  type Transaction,
} from "./bankTypes";
import { CreditorContactButton } from "./CreditorContactButton";
import { today as businessToday } from "@/lib/today";

/** HOOK (plan M12 step S1): rejection of a deterministic stage 1 proposal with a mandatory
 *  reason needs the decision log endpoint (`POST /banking/transactions/{id}/reject`), which
 *  the existing API does not offer yet. Set the path here once the backend package ships it;
 *  until then the button is not rendered. AI proposals are rejected through the existing
 *  `POST /ai/proposals/{id}/reject`. */
export const STAGE1_REJECT_PATH: ((txId: string) => string) | null = null;

/** HOOK (plan M12 step S1): `BookIn` has no `discount` field yet although
 *  `matching.book_payment` supports it. The field stays visible but disabled until the API
 *  accepts it; nothing is sent. */
export const API_SUPPORTS_DISCOUNT = false;

const MAX_LISTED = 25;
const SOURCE_KEY = { rule: "sourceRule", match: "sourceMatch", ai: "sourceAi" } as const;

type Settlement = { open_item_id: string; amount: string };

function reasons(value: Proposal["reasoning"]): string {
  if (!value) return "";
  return Array.isArray(value) ? value.join(", ") : value;
}

export type BookingDialogProps = {
  tx: Transaction;
  /** Property bank account of the partner half when known from the loaded list. */
  partnerBankAccountId?: string | null;
  /** Splits to start with (e.g. from a proposal chosen in the list). */
  initialSplits?: Split[];
  onClose: () => void;
  onBooked: (result: { journal_entry_id: string; number: string }) => void;
};

/** Manual booking of one bank transaction against the existing API (`POST
 *  /banking/transactions/{id}/book`): free choice of open items with partial amounts and
 *  splits, contra account search (no bank, system or inactive accounts), booking text,
 *  outgoing payments and transfer pairs. Proposals are shown with source, confidence and
 *  reasoning and can be taken over, never pre-selected; the booking needs an explicit
 *  confirmation step (7.4 Nr. 3 and 4, B02, B03). */
export function BookingDialog({ tx, partnerBankAccountId, initialSplits, onClose, onBooked }: BookingDialogProps) {
  const t = useTranslations("Bank.dialog");
  const tb = useTranslations("Bank");
  const incoming = Number(tx.amount) > 0;
  const amountCents = Math.abs(toCents(tx.amount));
  const isTransfer = tx.transfer_pair_id !== null;

  const [proposals, setProposals] = useState<Proposals | null>(null);
  const [accounts, setAccounts] = useState<LedgerAccount[]>([]);
  const [openItems, setOpenItems] = useState<OpenItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [settlements, setSettlements] = useState<Settlement[]>(
    (initialSplits ?? []).map((s) => ({ open_item_id: s.open_item_id, amount: s.amount })),
  );
  const [counterAccountId, setCounterAccountId] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [discount, setDiscount] = useState("");
  const [itemQuery, setItemQuery] = useState("");
  const [accountQuery, setAccountQuery] = useState("");
  const [transferElsewhere, setTransferElsewhere] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejected, setRejected] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      const p = await bff<Proposals>(`/api/bff/banking/transactions/${tx.id}/posting-proposals`);
      if (cancelled) return;
      if (!p.ok) {
        setError(p.message);
        setLoading(false);
        return;
      }
      setProposals(p.data);
      const ledgerId = p.data.ledger_id;
      if (ledgerId) {
        const today = businessToday();
        const [a, o] = await Promise.all([
          bff<LedgerAccount[]>(`/api/bff/accounting/ledgers/${ledgerId}/accounts`),
          bff<OpenItem[]>(`/api/bff/accounting/ledgers/${ledgerId}/open-items?as_of=${today}`),
        ]);
        if (cancelled) return;
        if (a.ok) setAccounts(a.data);
        else setError(a.message);
        if (o.ok) setOpenItems(o.data);
        else setError(o.message);
      }
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [tx.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Transfer pair: the partner bank account is preselected when the list knows the partner half.
  useEffect(() => {
    if (!isTransfer || transferElsewhere || counterAccountId || !partnerBankAccountId) return;
    const partner = accounts.find((a) => a.property_bank_account_id === partnerBankAccountId);
    if (partner) setCounterAccountId(partner.id);
  }, [accounts, isTransfer, transferElsewhere, counterAccountId, partnerBankAccountId]);

  const accountById = useMemo(() => new Map(accounts.map((a) => [a.id, a])), [accounts]);
  const itemById = useMemo(() => new Map(openItems.map((o) => [o.id, o])), [openItems]);
  const contraCandidates = useMemo(() => {
    const q = accountQuery.trim().toLowerCase();
    const pool = isTransfer && !transferElsewhere
      ? accounts.filter((a) => isPartnerBankAccountCandidate(a, tx.property_bank_account_id))
      : accounts.filter(isContraAccountCandidate);
    const hits = q ? pool.filter((a) => a.number.toLowerCase().includes(q) || a.name.toLowerCase().includes(q)) : pool;
    return hits.slice(0, MAX_LISTED);
  }, [accounts, accountQuery, isTransfer, transferElsewhere, tx.property_bank_account_id]);
  const itemCandidates = useMemo(() => {
    const q = itemQuery.trim().toLowerCase();
    const chosen = new Set(settlements.map((s) => s.open_item_id));
    const pool = openItems.filter((o) => !chosen.has(o.id));
    const hits = q
      ? pool.filter(
          (o) =>
            o.account_number.toLowerCase().includes(q) ||
            o.kind.toLowerCase().includes(q) ||
            (o.contract_id ?? "").toLowerCase().includes(q) ||
            (accountById.get(o.account_id)?.name ?? "").toLowerCase().includes(q),
        )
      : pool;
    return hits.slice(0, MAX_LISTED);
  }, [openItems, itemQuery, settlements, accountById]);

  const allocatedCents = settlements.reduce((sum, s) => sum + toCents(s.amount), 0);
  const discountCents = API_SUPPORTS_DISCOUNT ? toCents(discount) : 0;
  const restCents = amountCents + discountCents - allocatedCents;
  const settledAccounts = new Set(settlements.map((s) => itemById.get(s.open_item_id)?.account_id ?? s.open_item_id));
  const overAllocated = allocatedCents > amountCents + discountCents;
  // A partial amount that cannot be read ("1.250.00", letters) is reported as such; only a
  // readable amount of 0,00 or less counts as too small.
  const unreadableAmount = settlements.some((s) => parseAmount(s.amount) === null);
  const invalidAmount = settlements.some((s) => parseAmount(s.amount) !== null && toCents(s.amount) <= 0);
  const restAsCredit = restCents > 0 && !counterAccountId && settlements.length > 0 && settledAccounts.size === 1;
  const restNeedsContra = restCents > 0 && !counterAccountId && !restAsCredit;
  const transferNeedsPartner = isTransfer && !counterAccountId;
  const periodLocked = proposals?.object_period_lock?.locked === true;
  const canBook = !periodLocked && !busy && !loading && !overAllocated && !unreadableAmount && !invalidAmount && !restNeedsContra && !transferNeedsPartner;

  const applySplits = (splits: Split[] | undefined) => {
    setSettlements((splits ?? []).map((s) => ({ open_item_id: s.open_item_id, amount: s.amount })));
    setConfirming(false);
  };
  const addItem = (item: OpenItem) => {
    const remaining = Math.abs(toCents(item.remaining));
    const suggested = Math.max(0, Math.min(remaining, restCents));
    setSettlements((prev) => [...prev, { open_item_id: item.id, amount: fromCents(suggested > 0 ? suggested : remaining) }]);
    setConfirming(false);
  };
  const updateAmount = (id: string, value: string) => {
    setSettlements((prev) => prev.map((s) => (s.open_item_id === id ? { ...s, amount: value } : s)));
    setConfirming(false);
  };
  const removeItem = (id: string) => setSettlements((prev) => prev.filter((s) => s.open_item_id !== id));

  const book = async () => {
    setBusy(true);
    setError(null);
    const body: { settlements: Settlement[]; counter_account_id?: string; text?: string } = {
      settlements: isTransfer && !transferElsewhere ? [] : settlements.map((s) => ({ open_item_id: s.open_item_id, amount: fromCents(toCents(s.amount)) })),
    };
    if (counterAccountId) body.counter_account_id = counterAccountId;
    if (text.trim()) body.text = text.trim();
    const res = await bff<{ journal_entry_id: string; number: string }>(`/api/bff/banking/transactions/${tx.id}/book`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (res.ok) onBooked(res.data);
    else {
      setConfirming(false);
      setError(res.message);
    }
  };

  const rejectAi = async (proposalId: string) => {
    if (rejectReason.trim().length < 3) return;
    setBusy(true);
    const res = await bff(`/api/bff/ai/proposals/${proposalId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason: rejectReason.trim() }),
    });
    setBusy(false);
    if (res.ok) {
      setRejected((prev) => new Set(prev).add(proposalId));
      setRejecting(null);
      setRejectReason("");
    } else setError(res.message);
  };

  const kindLabel = (kind: string) => (tb.has(`kind.${kind}`) ? tb(`kind.${kind}`) : kind);
  const splitLabel = (s: Settlement) => {
    const item = itemById.get(s.open_item_id);
    const account = item ? accountById.get(item.account_id) : undefined;
    const base = account ? accountLabel(account) : (item?.account_number ?? s.open_item_id);
    // Several items of the same personal account: the due date keeps the rows apart.
    return item?.due_date ? `${base}, ${t("due", { date: formatDate(item.due_date) })}` : base;
  };
  const counterAccount = counterAccountId ? accountById.get(counterAccountId) : undefined;
  const confirmLines = [
    ...settlements.map((s) => `${splitLabel(s)} ${formatEur(fromCents(toCents(s.amount)))}`),
    ...(counterAccount ? [`${accountLabel(counterAccount)} ${formatEur(fromCents(isTransfer ? amountCents : restCents))}`] : []),
    ...(restAsCredit ? [t("restCredit")] : []),
  ];

  const proposalRow = (p: Proposal, key: string, splits: Split[] | undefined, ai?: AiProposal) => (
    <li key={key} className="flex flex-wrap items-center gap-2 text-xs" data-testid="proposal-row">
      <span className="rounded bg-surface-2 px-1 font-medium">{tb(SOURCE_KEY[p.source])}</span>
      <span>{kindLabel(p.kind)}</span>
      {p.confidence !== null && p.confidence !== undefined ? (
        <span className="tabular-nums">{tb("confidence", { value: Math.round(p.confidence * 100) })}</span>
      ) : null}
      {p.account_number ? <span className="text-muted">{p.account_number}</span> : null}
      <span className="text-muted">{reasons(p.reasoning)}</span>
      {p.unambiguous ? <span className="rounded bg-surface-2 px-1">{tb("unambiguous")}</span> : null}
      {ai && rejected.has(ai.id) ? (
        <span className={ui.badge}>{t("rejectedBadge")}</span>
      ) : (
        <>
          {splits && splits.length > 0 ? (
            <button type="button" className={ui.buttonSm} onClick={() => applySplits(splits)} disabled={busy}>
              {t("apply")}
            </button>
          ) : null}
          {ai ? (
            <button type="button" className={ui.buttonSm} onClick={() => setRejecting(ai.id)} disabled={busy}>
              {t("reject")}
            </button>
          ) : STAGE1_REJECT_PATH ? (
            <button type="button" className={ui.buttonSm} disabled>
              {t("reject")}
            </button>
          ) : null}
        </>
      )}
      {ai && rejecting === ai.id ? (
        <span className="flex w-full flex-wrap items-center gap-2">
          <input
            aria-label={t("rejectReason")}
            className={ui.input}
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder={t("rejectReason")}
          />
          <button type="button" className={ui.buttonSm} onClick={() => rejectAi(ai.id)} disabled={busy || rejectReason.trim().length < 3}>
            {t("rejectConfirm")}
          </button>
        </span>
      ) : null}
    </li>
  );

  return (
    <div className={`fixed inset-0 z-40 flex items-start justify-center overflow-y-auto p-4 ${ui.scrim}`} data-testid="booking-dialog">
      <div role="dialog" aria-modal="true" aria-labelledby="booking-dialog-title" className={`${ui.popover} my-6 w-full max-w-3xl p-4 sm:p-6`}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id="booking-dialog-title" className={ui.h2}>
              {t("title")}
            </h2>
            <p className="text-sm text-muted">
              {formatDate(tx.booking_date)} · {tx.counterpart_name ?? ""} · {tx.purpose ?? ""}
            </p>
            <p className="text-sm">
              <span className={ui.badge}>{incoming ? t("incoming") : t("outgoing")}</span>{" "}
              <span className="font-medium tabular-nums">{formatEur(tx.amount)}</span>
              {isTransfer ? <span className={`ml-2 ${ui.badgeInfo}`}>{t("transferBadge")}</span> : null}
            </p>
            {!isTransfer ? <CreditorContactButton transactionId={tx.id} outgoing={!incoming} /> : null}
          </div>
          <button type="button" className={ui.buttonSm} onClick={onClose}>
            {t("close")}
          </button>
        </div>
        {error ? (
          <p role="alert" className={`${ui.alert} mt-3`}>
            {error}
          </p>
        ) : null}
        {loading ? <p className="mt-3 text-sm text-muted">{t("loading")}</p> : null}
        {proposals ? (
          <section className="mt-4 flex flex-col gap-1">
            <h3 className={ui.h3}>{t("proposalsTitle")}</h3>
            <ul className="flex flex-col gap-1">
              {proposals.stage1.length + proposals.ai.length === 0 ? <li className="text-xs text-muted">{tb("noCandidates")}</li> : null}
              {proposals.stage1.map((p, i) => proposalRow(p, `s1-${i}`, p.splits))}
              {proposals.ai.map((p) => proposalRow({ ...p, source: "ai" }, `ai-${p.id}`, p.proposed?.splits ?? undefined, p))}
              <li className="text-xs text-muted">{tb("proposalNote")}</li>
              {STAGE1_REJECT_PATH === null ? <li className="text-xs text-muted">{t("rejectHook")}</li> : null}
            </ul>
          </section>
        ) : null}
        {proposals ? <AiPostingPanel txId={tx.id} canRequest /> : null}
        {isTransfer ? (
          <section className="mt-4 flex flex-col gap-2">
            <h3 className={ui.h3}>{t("transferTitle")}</h3>
            <p className="text-xs text-muted">{t("transferHint")}</p>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={transferElsewhere}
                onChange={(e) => {
                  setTransferElsewhere(e.target.checked);
                  setCounterAccountId(null);
                  setConfirming(false);
                }}
              />
              {t("transferOther")}
            </label>
          </section>
        ) : (
          <section className="mt-4 grid gap-4 md:grid-cols-2">
            <div className="flex flex-col gap-2">
              <h3 className={ui.h3}>{t("openItemsTitle")}</h3>
              <input aria-label={t("searchOpenItems")} className={ui.input} placeholder={t("searchOpenItems")} value={itemQuery} onChange={(e) => setItemQuery(e.target.value)} />
              <ul className="flex max-h-64 flex-col gap-1 overflow-y-auto text-xs" data-testid="open-item-candidates">
                {itemCandidates.length === 0 ? <li className="text-muted">{t("noOpenItems")}</li> : null}
                {itemCandidates.map((o) => (
                  <li key={o.id} className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{accountById.get(o.account_id) ? accountLabel(accountById.get(o.account_id)!) : o.account_number}</span>
                    <span className="text-muted">{o.kind}</span>
                    {o.due_date ? <span className="text-muted">{t("due", { date: formatDate(o.due_date) })}</span> : null}
                    <span className="tabular-nums">{t("remaining", { amount: formatEur(o.remaining) })}</span>
                    <button type="button" className={ui.buttonSm} onClick={() => addItem(o)} disabled={busy}>
                      {t("add")}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
            <div className="flex flex-col gap-2">
              <h3 className={ui.h3}>{t("settlementsTitle")}</h3>
              {settlements.length === 0 ? <p className="text-xs text-muted">{t("noSettlements")}</p> : null}
              <ul className="flex flex-col gap-2" data-testid="settlements">
                {settlements.map((s) => (
                  <li key={s.open_item_id} className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="font-medium">{splitLabel(s)}</span>
                    <input
                      aria-label={t("splitAmount", { account: splitLabel(s) })}
                      className={`${ui.input} max-w-32`}
                      inputMode="decimal"
                      value={s.amount}
                      onChange={(e) => updateAmount(s.open_item_id, e.target.value)}
                    />
                    <button type="button" className={ui.buttonSm} onClick={() => removeItem(s.open_item_id)} disabled={busy}>
                      {t("remove")}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </section>
        )}
        <section className="mt-4 grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-2">
            <h3 className={ui.h3}>{isTransfer && !transferElsewhere ? t("partnerBank") : t("contraAccount")}</h3>
            {counterAccount ? (
              <p className="flex items-center gap-2 text-sm">
                <span className="font-medium" data-testid="contra-selected">
                  {accountLabel(counterAccount)}
                </span>
                <button type="button" className={ui.buttonSm} onClick={() => setCounterAccountId(null)} disabled={busy}>
                  {t("contraClear")}
                </button>
              </p>
            ) : (
              <p className="text-xs text-muted">{t("contraNone")}</p>
            )}
            <input aria-label={t("contraSearch")} className={ui.input} placeholder={t("contraSearch")} value={accountQuery} onChange={(e) => setAccountQuery(e.target.value)} />
            <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto text-xs" data-testid="contra-candidates">
              {contraCandidates.map((a) => (
                <li key={a.id}>
                  <button
                    type="button"
                    className={`${ui.buttonSm} w-full justify-start`}
                    onClick={() => {
                      setCounterAccountId(a.id);
                      setConfirming(false);
                    }}
                    disabled={busy}
                  >
                    {accountLabel(a)}
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div className="flex flex-col gap-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("text")}</span>
              <input className={ui.input} maxLength={500} value={text} onChange={(e) => setText(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("discount")}</span>
              <input
                className={ui.input}
                inputMode="decimal"
                value={discount}
                onChange={(e) => setDiscount(e.target.value)}
                disabled={!API_SUPPORTS_DISCOUNT}
                aria-describedby="discount-hint"
              />
            </label>
            {!API_SUPPORTS_DISCOUNT ? (
              <span id="discount-hint" className={ui.help}>
                {t("discountHook")}
              </span>
            ) : null}
            <dl className="grid grid-cols-2 gap-x-3 text-sm">
              <dt className="text-muted">{t("amountLabel")}</dt>
              <dd className="text-right tabular-nums">{formatEur(fromCents(amountCents))}</dd>
              <dt className="text-muted">{t("allocatedLabel")}</dt>
              <dd className="text-right tabular-nums" data-testid="allocated">
                {formatEur(fromCents(allocatedCents))}
              </dd>
              <dt className="text-muted">{t("restLabel")}</dt>
              <dd className="text-right tabular-nums" data-testid="rest">
                {formatEur(fromCents(isTransfer && !transferElsewhere ? 0 : restCents))}
              </dd>
            </dl>
            {overAllocated ? <p className={ui.error}>{t("overAllocated")}</p> : null}
            {unreadableAmount ? <p className={ui.error}>{t("unreadableAmount")}</p> : null}
            {invalidAmount ? <p className={ui.error}>{t("invalidAmount")}</p> : null}
            {restNeedsContra && !isTransfer ? <p className={ui.error}>{t("restNeedsContra")}</p> : null}
            {restAsCredit ? <p className={ui.help}>{t("restCredit")}</p> : null}
            {transferNeedsPartner ? <p className={ui.error}>{t("transferNeedsPartner")}</p> : null}
          </div>
        </section>
        <div className="mt-4 flex flex-col gap-2">
          {periodLocked ? (
            <p role="alert" className={ui.error} data-testid="period-lock-hint">
              {t("periodLocked", { code: proposals?.object_period_lock?.code ?? "MHVP-ACC-0030" })}
            </p>
          ) : null}
          {confirming ? (
            <div className={ui.notice} data-testid="confirm-box">
              <p>{t("confirmText", { amount: formatEur(tx.amount) })}</p>
              <ul className="mt-1 list-disc pl-5">
                {confirmLines.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className={ui.formActions}>
            {confirming ? (
              <>
                <button type="button" className={ui.primary} onClick={book} disabled={!canBook}>
                  {t("confirm")}
                </button>
                <button type="button" className={ui.secondary} onClick={() => setConfirming(false)} disabled={busy}>
                  {t("back")}
                </button>
              </>
            ) : (
              <button type="button" className={ui.primary} onClick={() => setConfirming(true)} disabled={!canBook}>
                {t("book")}
              </button>
            )}
            <button type="button" className={ui.secondary} onClick={onClose} disabled={busy}>
              {t("close")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
