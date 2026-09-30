"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type LedgerAccountOption = { id: string; number: string; name: string; category: string; active: boolean };

type Line = { account_id: string; debit: string; credit: string; text: string };
type Mode = "manual" | "cost_transfer" | "interest";

const MANUAL_KINDS = ["custom", "opening_balance", "bank_transfer"] as const;
const emptyLine = (): Line => ({ account_id: "", debit: "", credit: "", text: "" });

/** "1.234,56" or "1234.56" to the API decimal string; empty stays "0". No float arithmetic. */
export function toDecimal(value: string): string {
  const v = value.trim().replace(/\s/g, "");
  if (!v) return "0";
  return v.includes(",") ? v.replace(/\./g, "").replace(",", ".") : v;
}

/** Sum of decimal strings in cents (integers), so that the balance check stays exact. */
export function sumCents(values: string[]): number {
  return values.reduce((acc, value) => {
    const [whole = "0", frac = ""] = toDecimal(value).split(".");
    const sign = whole.startsWith("-") ? -1 : 1;
    const cents = Math.abs(Number.parseInt(whole, 10) || 0) * 100 + (Number.parseInt((frac + "00").slice(0, 2), 10) || 0);
    return acc + sign * cents;
  }, 0);
}

/** Draft entry (M10-02), cost transfer and interest (M10-06). Only drafts are created here;
 *  posting is a separate action in the journal. */
export function JournalEntryForm({ ledgerId, accounts, today }: { ledgerId: string; accounts: LedgerAccountOption[]; today: string }) {
  const t = useTranslations("Bookkeeping");
  const router = useRouter();
  const active = accounts.filter((a) => a.active);
  const [mode, setMode] = useState<Mode>("manual");
  const [kind, setKind] = useState<(typeof MANUAL_KINDS)[number]>("custom");
  const [bookingDate, setBookingDate] = useState(today);
  const [text, setText] = useState("");
  const [lines, setLines] = useState<Line[]>([emptyLine(), emptyLine()]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [amount, setAmount] = useState("");
  const [direction, setDirection] = useState<"credit" | "debit">("credit");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const debit = sumCents(lines.map((l) => l.debit));
  const credit = sumCents(lines.map((l) => l.credit));
  const option = (a: LedgerAccountOption) => (
    <option key={a.id} value={a.id}>
      {a.number} {a.name}
    </option>
  );
  const byCategory = (...cats: string[]) => active.filter((a) => cats.includes(a.category));
  const setLine = (i: number, patch: Partial<Line>) => setLines((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setDone(null);
    let path = `/api/bff/accounting/ledgers/${ledgerId}/entries`;
    let body: Record<string, unknown>;
    if (mode === "manual") {
      if (debit !== credit || debit === 0) {
        setError(t("entry.unbalanced"));
        return;
      }
      body = {
        kind,
        booking_date: bookingDate,
        text,
        lines: lines
          .filter((l) => l.account_id)
          .map((l) => ({ account_id: l.account_id, debit: toDecimal(l.debit), credit: toDecimal(l.credit), text: l.text || null })),
      };
    } else if (mode === "cost_transfer") {
      path += "/cost-transfer";
      body = { booking_date: bookingDate, text, from_account_id: from, to_account_id: to, amount: toDecimal(amount) };
    } else {
      path += "/interest";
      body = { booking_date: bookingDate, text, bank_account_id: from, interest_account_id: to, amount: toDecimal(amount), direction };
    }
    setBusy(true);
    const res = await bff<{ id: string }>(path, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setDone(t("entry.created"));
    setText("");
    setAmount("");
    setLines([emptyLine(), emptyLine()]);
    router.refresh();
  };

  return (
    <form onSubmit={submit} className={`${ui.card} flex flex-col gap-3`} aria-label={t("entry.title")}>
      <h3 className="text-sm font-semibold">{t("entry.title")}</h3>
      <p className={ui.help}>{t("entry.help")}</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("entry.mode")}</span>
          <select className={ui.input} value={mode} onChange={(e) => { setMode(e.target.value as Mode); setFrom(""); setTo(""); }}>
            {(["manual", "cost_transfer", "interest"] as const).map((m) => (
              <option key={m} value={m}>
                {t(`entry.modes.${m}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("entry.bookingDate")}</span>
          <input type="date" required className={ui.input} value={bookingDate} onChange={(e) => setBookingDate(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("entry.text")}</span>
          <input required minLength={3} maxLength={500} className={ui.input} value={text} onChange={(e) => setText(e.target.value)} />
        </label>
      </div>
      {mode === "manual" ? (
        <>
          <label className="flex flex-col gap-1 sm:w-1/3">
            <span className={ui.label}>{t("entry.kind")}</span>
            <select className={ui.input} value={kind} onChange={(e) => setKind(e.target.value as (typeof MANUAL_KINDS)[number])}>
              {MANUAL_KINDS.map((k) => (
                <option key={k} value={k}>
                  {t(`entry.kinds.${k}`)}
                </option>
              ))}
            </select>
          </label>
          {kind === "opening_balance" ? <p className={ui.notice}>{t("entry.openingNotice")}</p> : null}
          <div className="flex flex-col gap-2">
            {lines.map((line, i) => (
              <div key={i} className="grid gap-2 sm:grid-cols-[2fr_1fr_1fr_2fr_auto]">
                <select aria-label={t("entry.account")} className={ui.input} value={line.account_id} onChange={(e) => setLine(i, { account_id: e.target.value })}>
                  <option value="">{t("entry.chooseAccount")}</option>
                  {active.map(option)}
                </select>
                <input aria-label={t("entry.debit")} inputMode="decimal" placeholder={t("entry.debit")} className={ui.input} value={line.debit} onChange={(e) => setLine(i, { debit: e.target.value })} />
                <input aria-label={t("entry.credit")} inputMode="decimal" placeholder={t("entry.credit")} className={ui.input} value={line.credit} onChange={(e) => setLine(i, { credit: e.target.value })} />
                <input aria-label={t("entry.lineText")} placeholder={t("entry.lineText")} className={ui.input} value={line.text} onChange={(e) => setLine(i, { text: e.target.value })} />
                <button type="button" className={ui.buttonSm} disabled={lines.length <= 2} onClick={() => setLines((rows) => rows.filter((_, j) => j !== i))}>
                  {t("entry.removeLine")}
                </button>
              </div>
            ))}
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className={ui.buttonSm} onClick={() => setLines((rows) => [...rows, emptyLine()])}>
                {t("entry.addLine")}
              </button>
              <span className="text-sm tabular-nums" data-testid="entry-sums">
                {t("entry.sums", { debit: formatEur(debit / 100), credit: formatEur(credit / 100) })}
              </span>
            </div>
          </div>
        </>
      ) : (
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{mode === "cost_transfer" ? t("entry.fromCost") : t("entry.bankAccount")}</span>
            <select required className={ui.input} value={from} onChange={(e) => setFrom(e.target.value)}>
              <option value="">{t("entry.chooseAccount")}</option>
              {(mode === "cost_transfer" ? byCategory("cost") : byCategory("bank", "reserve")).map(option)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{mode === "cost_transfer" ? t("entry.toCost") : t("entry.interestAccount")}</span>
            <select required className={ui.input} value={to} onChange={(e) => setTo(e.target.value)}>
              <option value="">{t("entry.chooseAccount")}</option>
              {(mode === "cost_transfer" ? byCategory("cost") : byCategory(direction === "credit" ? "revenue" : "cost")).map(option)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("entry.amount")}</span>
            <input required inputMode="decimal" className={ui.input} value={amount} onChange={(e) => setAmount(e.target.value)} />
          </label>
          {mode === "interest" ? (
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("entry.direction")}</span>
              <select className={ui.input} value={direction} onChange={(e) => { setDirection(e.target.value as "credit" | "debit"); setTo(""); }}>
                <option value="credit">{t("entry.directions.credit")}</option>
                <option value="debit">{t("entry.directions.debit")}</option>
              </select>
            </label>
          ) : null}
          {mode === "interest" ? <p className={`${ui.help} sm:col-span-3`}>{t("entry.interestTaxNote")}</p> : null}
        </div>
      )}
      <div className={ui.formActions}>
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("entry.save")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
      {done ? (
        <p role="status" className={ui.success}>
          {done}
        </p>
      ) : null}
    </form>
  );
}
