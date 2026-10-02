"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import type { ReferenceRate } from "@/components/settings/DepositInterestRatesAdmin";
import { bff } from "@/lib/bff";
import { formatDate, formatDecimal, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type DepositMovementOut = { id: string; date: string; amount: string; kind: "payment" | "interest" | "payout" | "offset"; reason: string | null; review_required: boolean };
export type DepositOut = {
  id: string;
  contract_id: string;
  kind: string;
  amount_due: string;
  installments: number;
  valid_from: string;
  valid_to: string | null;
  interest_rule: string | null;
  status: string;
  received: string;
  balance: string;
  outstanding: string;
  movements: DepositMovementOut[];
};
export type InterestMode = "individual" | "reference_rate" | "deposit_rates" | "none";
export type DepositSettlementOut = {
  id: string | null;
  deposit_id: string;
  status: "draft" | "released";
  settlement_date: string;
  interest_mode: InterestMode;
  interest_years: { year: number; rate: string | null; days: number; amount: string }[];
  deductions: { label: string; amount: string }[];
  principal_paid: string;
  offsets_recorded: string;
  payouts_recorded: string;
  interest_recorded: string;
  balance_before_interest: string;
  interest_total: string;
  deductions_total: string;
  payout_amount: string;
  note: string | null;
  draft_only: boolean;
};

type DeductionRow = { label: string; amount: string };

const MODES: InterestMode[] = ["individual", "reference_rate", "deposit_rates", "none"];

/** Amount input "1.234,56" or "1234.56" -> API string "1234.56" (no float). */
export function parseAmount(value: string): string | null {
  const raw = value.trim();
  if (!raw) return null;
  const normalised = raw.includes(",") ? raw.replace(/\./g, "").replace(",", ".") : raw;
  if (!/^\d+(\.\d{1,2})?$/.test(normalised)) return null;
  const [whole, frac = ""] = normalised.split(".");
  return `${whole}.${frac.padEnd(2, "0")}`;
}

/** Calendar years from the first payment to the settlement date (matches the API span). */
export function yearSpan(deposit: DepositOut, settlementDate: string): number[] {
  const payments = deposit.movements.filter((m) => m.kind !== "interest").map((m) => Number(m.date.slice(0, 4)));
  const end = Number(settlementDate.slice(0, 4));
  if (payments.length === 0 || !Number.isInteger(end)) return [];
  const start = Math.min(...payments);
  if (end < start) return [];
  return Array.from({ length: end - start + 1 }, (_, i) => start + i);
}

/** Recorded interest movements summed per year (prefill for the individual mode), as cent integers. */
function recordedInterestByYear(deposit: DepositOut): Record<number, string> {
  const cents: Record<number, bigint> = {};
  for (const m of deposit.movements) {
    if (m.kind !== "interest") continue;
    const y = Number(m.date.slice(0, 4));
    const [whole = "0", frac = ""] = m.amount.split(".");
    cents[y] = (cents[y] ?? 0n) + BigInt(whole) * 100n + BigInt(frac.padEnd(2, "0").slice(0, 2));
  }
  const out: Record<number, string> = {};
  for (const [y, c] of Object.entries(cents)) out[Number(y)] = `${c / 100n}.${String(c % 100n).padStart(2, "0")}`;
  return out;
}

function SettlementView({ s }: { s: DepositSettlementOut }) {
  const t = useTranslations("Deposits");
  return (
    <div className="flex flex-col gap-2 text-sm">
      <dl className="grid gap-1 sm:grid-cols-2">
        <dt className={ui.label}>{t("settlement.date")}</dt>
        <dd>{formatDate(s.settlement_date)}</dd>
        <dt className={ui.label}>{t("settlement.mode")}</dt>
        <dd>{t(`modes.${s.interest_mode}`)}</dd>
        <dt className={ui.label}>{t("settlement.principalPaid")}</dt>
        <dd>{formatEur(s.principal_paid)}</dd>
        <dt className={ui.label}>{t("settlement.offsetsRecorded")}</dt>
        <dd>{formatEur(s.offsets_recorded)}</dd>
        <dt className={ui.label}>{t("settlement.payoutsRecorded")}</dt>
        <dd>{formatEur(s.payouts_recorded)}</dd>
        <dt className={ui.label}>{t("settlement.balanceBeforeInterest")}</dt>
        <dd>{formatEur(s.balance_before_interest)}</dd>
        <dt className={ui.label}>{t("settlement.interestRecorded")}</dt>
        <dd>{formatEur(s.interest_recorded)}</dd>
      </dl>
      {s.interest_years.length > 0 ? (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("settlement.year")}</th>
                <th>{t("settlement.rate")}</th>
                <th>{t("settlement.days")}</th>
                <th>{t("settlement.interest")}</th>
              </tr>
            </thead>
            <tbody>
              {s.interest_years.map((y) => (
                <tr key={y.year}>
                  <td>{y.year}</td>
                  <td>{y.rate ? `${formatDecimal(y.rate, 5)} %` : t("settlement.entered")}</td>
                  <td>{y.days}</td>
                  <td>{formatEur(y.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <dl className="grid gap-1 sm:grid-cols-2">
        <dt className={ui.label}>{t("settlement.interestTotal")}</dt>
        <dd>{formatEur(s.interest_total)}</dd>
        {s.deductions.map((d, i) => (
          <DeductionLine key={i} label={d.label} amount={d.amount} />
        ))}
        <dt className={ui.label}>{t("settlement.deductionsTotal")}</dt>
        <dd>{formatEur(s.deductions_total)}</dd>
        <dt className={ui.label}>{t("settlement.payoutAmount")}</dt>
        <dd className="font-semibold">{formatEur(s.payout_amount)}</dd>
      </dl>
      {s.note ? <p className="whitespace-pre-line">{s.note}</p> : null}
    </div>
  );
}

function DeductionLine({ label, amount }: { label: string; amount: string }) {
  return (
    <>
      <dt className={ui.label}>{label}</dt>
      <dd>{formatEur(amount)}</dd>
    </>
  );
}

const MOVEMENT_KINDS = ["payment", "interest", "payout", "offset"] as const;

/** GAF-27: record a deposit movement (POST deposits/{id}/movements). No posting arises here;
 *  payout and offset need a reason (API rule). */
export function DepositMovementForm({ depositId }: { depositId: string }) {
  const t = useTranslations("LedgerExtras.deposit");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [amount, setAmount] = useState("");
  const [kind, setKind] = useState<(typeof MOVEMENT_KINDS)[number]>("payment");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const needsReason = kind === "payout" || kind === "offset";
  if (!open) {
    return (
      <button type="button" className={`${ui.buttonSm} self-start`} onClick={() => setOpen(true)}>
        {t("movementTitle")}
      </button>
    );
  }
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaved(false);
    const parsed = parseAmount(amount);
    if (!parsed || Number(parsed) <= 0) {
      setError(t("amount"));
      return;
    }
    setBusy(true);
    const res = await bff(`/api/bff/deposits/${depositId}/movements`, {
      method: "POST",
      body: JSON.stringify({ date, amount: parsed, kind, reason: reason.trim() || null }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setSaved(true);
    setAmount("");
    setReason("");
    router.refresh();
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-2 rounded-md border border-border p-3" aria-label={t("movementTitle")}>
      <h3 className={ui.label}>{t("movementTitle")}</h3>
      <p className={ui.notice}>{t("movementHelp")}</p>
      <div className="grid gap-2 sm:grid-cols-4">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("date")}</span>
          <input type="date" required className={ui.input} value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("amount")}</span>
          <input required inputMode="decimal" className={ui.input} value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0,00" />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("kind")}</span>
          <select className={ui.input} value={kind} onChange={(e) => setKind(e.target.value as (typeof MOVEMENT_KINDS)[number])}>
            {MOVEMENT_KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`kinds.${k}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("reason")}</span>
          <input required={needsReason} className={ui.input} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
      </div>
      <div className={ui.formActions}>
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("save")}
        </button>
        <button type="button" className={ui.secondary} onClick={() => setOpen(false)}>
          {t("close")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
      {saved ? (
        <p role="status" className={ui.success}>
          {t("saved")}
        </p>
      ) : null}
    </form>
  );
}

/** GAF-27: yearly interest draft run for all deposits with a rate (drafts only, nothing posted). */
export function DepositInterestRun() {
  const t = useTranslations("LedgerExtras.deposit");
  const router = useRouter();
  const [year, setYear] = useState(String(new Date().getFullYear() - 1));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    const res = await bff<{ year: number; created: number; skipped: unknown[] }>("/api/bff/deposit-interest-drafts/run", {
      method: "POST",
      body: JSON.stringify({ year: Number(year) }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setResult(t("runResult", { created: res.data.created, skipped: res.data.skipped.length }));
    router.refresh();
  };
  return (
    <form onSubmit={run} className="flex flex-col gap-2 rounded-md border border-border p-3" aria-label={t("runTitle")}>
      <h3 className={ui.label}>{t("runTitle")}</h3>
      <p className={ui.help}>{t("runHelp")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("year")}</span>
          <input type="number" min={1900} max={2200} required className={ui.input} value={year} onChange={(e) => setYear(e.target.value)} />
        </label>
        <button type="submit" className={ui.secondary} disabled={busy || !year}>
          {t("run")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
      {result ? (
        <p role="status" className={ui.success}>
          {result}
        </p>
      ) : null}
    </form>
  );
}

/** Kautionen eines Mietvertrags (M5-02): Stand, Bewegungen, gespeicherte Abrechnungsentwürfe und
 *  das Formular Kautionsabrechnung mit Zinsart (individuell je Jahr, Referenzzinssatz je Jahr,
 *  keine Verzinsung). Der Entwurf bucht nichts und zahlt nichts aus; die Freigabe liegt hinter G3. */
export function DepositPanel({
  deposits,
  settlements,
  rates,
  contractEndDate,
  canUpdate,
  contractId,
}: {
  deposits: DepositOut[];
  settlements: Record<string, DepositSettlementOut[]>;
  rates: ReferenceRate[];
  contractEndDate: string | null;
  canUpdate: boolean;
  contractId: string;
}) {
  const t = useTranslations("Deposits");
  const router = useRouter();
  const [docBusy, setDocBusy] = useState<string | null>(null);
  const [docError, setDocError] = useState<string | null>(null);

  const createDocument = async (settlementId: string) => {
    setDocBusy(settlementId);
    setDocError(null);
    const res = await bff<{ document_id: string }>(`/api/bff/contracts/${contractId}/deposit-settlements/${settlementId}/document`, {
      method: "POST",
    });
    setDocBusy(null);
    if (!res.ok) {
      setDocError(res.message);
      return;
    }
    router.refresh();
  };
  const [open, setOpen] = useState<string | null>(null);
  const [date, setDate] = useState(contractEndDate ?? new Date().toISOString().slice(0, 10));
  const [mode, setMode] = useState<InterestMode>("individual");
  const [interest, setInterest] = useState<Record<number, string>>({});
  const [deductions, setDeductions] = useState<DeductionRow[]>([]);
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState<DepositSettlementOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const deposit = deposits.find((d) => d.id === open) ?? null;
  const years = useMemo(() => (deposit ? yearSpan(deposit, date) : []), [deposit, date]);
  const rateByYear = useMemo(() => Object.fromEntries(rates.map((r) => [r.year, r.rate])), [rates]);
  const missingRates = mode === "reference_rate" ? years.filter((y) => rateByYear[y] === undefined) : [];

  const start = (d: DepositOut) => {
    setOpen(d.id);
    setPreview(null);
    setError(null);
    setSaved(false);
    setInterest(recordedInterestByYear(d));
    setDeductions([]);
  };

  const body = () => {
    const interestYears = mode === "individual" ? years.map((y) => ({ year: y, amount: parseAmount(interest[y] ?? "") ?? "0.00" })) : [];
    const rows = deductions.filter((d) => d.label.trim() || d.amount.trim());
    if (rows.some((d) => !d.label.trim() || parseAmount(d.amount) === null)) return null;
    return {
      settlement_date: date,
      interest_mode: mode,
      interest_years: interestYears,
      deductions: rows.map((d) => ({ label: d.label.trim(), amount: parseAmount(d.amount) })),
      note: note.trim() || null,
    };
  };

  const send = async (save: boolean) => {
    if (!deposit) return;
    const payload = body();
    if (!payload) {
      setError(t("errors.deductionInvalid"));
      return;
    }
    setBusy(true);
    setError(null);
    setSaved(false);
    const res = await bff<DepositSettlementOut>(`/api/bff/deposits/${deposit.id}/settlements${save ? "" : "/preview"}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setPreview(res.data);
    if (save) {
      setSaved(true);
      router.refresh();
    }
  };

  return (
    <section className={ui.card}>
      <h2 className={ui.h2}>{t("title")}</h2>
      {deposits.length === 0 ? (
        <p className={ui.help}>{t("none")}</p>
      ) : (
        <ul className="flex flex-col gap-3 text-sm">
          {deposits.map((d) => (
            <li key={d.id} className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-3">
                <span className={ui.badge}>{t(`kinds.${d.kind}`)}</span>
                <span>
                  {t("amountDue")}: {formatEur(d.amount_due)}
                </span>
                <span>
                  {t("received")}: {formatEur(d.received)}
                </span>
                <span>
                  {t("balance")}: {formatEur(d.balance)}
                </span>
                {canUpdate && open !== d.id ? (
                  <button type="button" className={ui.buttonSm} onClick={() => start(d)}>
                    {t("settlement.start")}
                  </button>
                ) : null}
              </div>
              {d.movements.length > 0 ? (
                <ul className="text-xs text-muted">
                  {d.movements.map((m) => (
                    <li key={m.id}>
                      {formatDate(m.date)}, {t(`movementKinds.${m.kind}`)}, {formatEur(m.amount)}
                      {m.reason ? `, ${m.reason}` : ""}
                      {m.review_required ? `, ${t("reviewRequired")}` : ""}
                    </li>
                  ))}
                </ul>
              ) : null}
              {canUpdate && d.status !== "settled" ? <DepositMovementForm depositId={d.id} /> : null}
              {(settlements[d.id] ?? []).map((s) => (
                <details key={s.id ?? s.settlement_date} className="rounded-md border border-border p-2">
                  <summary className="cursor-pointer">
                    {t("settlement.savedDraft")} {formatDate(s.settlement_date)}, {t(`modes.${s.interest_mode}`)}, {t("settlement.payoutAmount")} {formatEur(s.payout_amount)}
                    {s.status === "draft" ? ` (${t("settlement.draft")})` : ""}
                  </summary>
                  <SettlementView s={s} />
                  {canUpdate && s.id ? (
                    <div className="mt-2 flex flex-col gap-1">
                      <button
                        type="button"
                        className={ui.buttonSm}
                        data-testid="deposit-settlement-create-document"
                        disabled={docBusy === s.id}
                        onClick={() => void createDocument(s.id!)}
                      >
                        {t("settlement.createDocument")}
                      </button>
                      {docError && docBusy === null ? (
                        <p role="alert" className={ui.error}>
                          {docError}
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                </details>
              ))}
            </li>
          ))}
        </ul>
      )}
      {deposit ? (
        <form
          className="mt-4 flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            void send(false);
          }}
        >
          <h3 className={ui.h2}>{t("settlement.title")}</h3>
          <p className={ui.notice}>{t("settlement.notice")}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("settlement.date")}</span>
              <input type="date" className={ui.input} value={date} onChange={(e) => setDate(e.target.value)} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("settlement.mode")}</span>
              <select className={ui.input} value={mode} onChange={(e) => setMode(e.target.value as InterestMode)}>
                {MODES.map((m) => (
                  <option key={m} value={m}>
                    {t(`modes.${m}`)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {mode === "individual" ? (
            <div className="grid gap-2 sm:grid-cols-3">
              {years.map((y) => (
                <label key={y} className="flex flex-col gap-1">
                  <span className={ui.label}>{t("settlement.interestFor", { year: y })}</span>
                  <input className={ui.input} value={interest[y] ?? ""} onChange={(e) => setInterest({ ...interest, [y]: e.target.value })} placeholder="0,00" inputMode="decimal" />
                </label>
              ))}
              <p className={`${ui.help} sm:col-span-3`}>{t("settlement.individualHelp")}</p>
            </div>
          ) : null}
          {mode === "reference_rate" ? (
            <div className="flex flex-col gap-1 text-sm">
              {years.map((y) => (
                <span key={y}>
                  {y}: {rateByYear[y] !== undefined ? `${formatDecimal(rateByYear[y], 5)} %` : t("settlement.rateMissing")}
                </span>
              ))}
              {missingRates.length > 0 ? (
                <p role="alert" className={ui.error}>
                  {t("settlement.rateMissingHint", { years: missingRates.join(", ") })}
                </p>
              ) : null}
              <p className={ui.help}>{t("settlement.referenceHelp")}</p>
            </div>
          ) : null}
          <fieldset className="flex flex-col gap-2">
            <legend className={ui.label}>{t("settlement.deductions")}</legend>
            {deductions.map((d, i) => (
              <div key={i} className="grid gap-2 sm:grid-cols-[2fr_1fr_auto]">
                <input className={ui.input} aria-label={t("settlement.deductionLabel")} value={d.label} onChange={(e) => setDeductions(deductions.map((row, j) => (j === i ? { ...row, label: e.target.value } : row)))} />
                <input className={ui.input} aria-label={t("settlement.deductionAmount")} value={d.amount} placeholder="0,00" inputMode="decimal" onChange={(e) => setDeductions(deductions.map((row, j) => (j === i ? { ...row, amount: e.target.value } : row)))} />
                <button type="button" className={ui.buttonSm} onClick={() => setDeductions(deductions.filter((_, j) => j !== i))}>
                  {t("settlement.removeDeduction")}
                </button>
              </div>
            ))}
            <button type="button" className={ui.buttonSm} onClick={() => setDeductions([...deductions, { label: "", amount: "" }])}>
              {t("settlement.addDeduction")}
            </button>
          </fieldset>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("settlement.note")}</span>
            <textarea className={ui.input} value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
          </label>
          {error ? (
            <p role="alert" className={ui.alert}>
              {error}
            </p>
          ) : null}
          {saved ? (
            <p role="status" className={ui.success}>
              {t("settlement.saved")}
            </p>
          ) : null}
          {preview ? (
            <div className="rounded-md border border-border p-3">
              <h4 className={ui.label}>{preview.id ? t("settlement.savedDraft") : t("settlement.preview")}</h4>
              <SettlementView s={preview} />
            </div>
          ) : null}
          <div className={ui.formActions}>
            <button type="submit" className={ui.secondary} disabled={busy || missingRates.length > 0}>
              {t("settlement.compute")}
            </button>
            <button type="button" className={ui.primary} disabled={busy || missingRates.length > 0} onClick={() => void send(true)}>
              {t("settlement.save")}
            </button>
            <button type="button" className={ui.button} onClick={() => setOpen(null)}>
              {t("settlement.cancel")}
            </button>
          </div>
        </form>
      ) : null}
      {canUpdate && deposits.length > 0 ? <DepositInterestRun /> : null}
    </section>
  );
}
