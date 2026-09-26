"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** W10 (A59) and W04 (A60) forms: loans, insurance claims, measures and the explained
 *  differences of the cash flow reconciliation. Everything is recording; nothing posts. */

type Account = { id: string; number: string; name: string };
const MONEY = /^-?\d+([.,]\d{1,2})?$/;
const num = (v: string) => v.replace(",", ".");

function useCall() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const call = async <T,>(path: string, body: unknown, method = "POST"): Promise<T | null> => {
    setBusy(true);
    setError(null);
    const res = await bff<T>(`/api/bff/hoa/${path}`, { method, body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return null;
    }
    router.refresh();
    return res.data;
  };
  return { busy, error, call, router };
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className={ui.label}>{label}</span>
      {children}
    </label>
  );
}

function ErrorLine({ error }: { error: string | null }) {
  return error ? (
    <p role="alert" className={ui.alert}>
      {error}
    </p>
  ) : null;
}

/** Creates a loan, an insurance claim or a measure draft and opens it. */
export function FinanceCreate({
  kind,
  ledgerId,
  basePath,
  loanAccounts = [],
}: {
  kind: "loan" | "claim" | "measure";
  ledgerId: string;
  basePath: string;
  loanAccounts?: Account[];
}) {
  const t = useTranslations("HoaFinance");
  const { busy, error, call, router } = useCall();
  const [f, setF] = useState<Record<string, string>>({ kind: "undecided", account: "" });
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF((s) => ({ ...s, [k]: e.target.value }));
  const valid =
    kind === "loan"
      ? (f.lender ?? "").trim().length >= 2 && MONEY.test(f.principal ?? "") && MONEY.test(f.rate ?? "") && !!f.start && (f.purpose ?? "").trim().length >= 3
      : kind === "claim"
        ? (f.title ?? "").trim().length >= 3 && !!f.damageDate
        : (f.title ?? "").trim().length >= 3 && MONEY.test(f.costFrame ?? "") && (f.kind === "undecided" || (f.kindBasis ?? "").trim().length >= 3);
  const create = async () => {
    const body =
      kind === "loan"
        ? {
            ledger_id: ledgerId,
            lender: (f.lender ?? "").trim(),
            principal: num(f.principal ?? ""),
            interest_rate_percent: num(f.rate ?? ""),
            term_months: f.term ? Number(f.term) : null,
            instalment: f.instalment ? num(f.instalment) : null,
            start_date: f.start,
            purpose: (f.purpose ?? "").trim(),
            account_id: f.account || null,
          }
        : kind === "claim"
          ? {
              ledger_id: ledgerId,
              title: (f.title ?? "").trim(),
              damage_date: f.damageDate,
              insurer: f.insurer?.trim() || null,
              policy_reference: f.policy?.trim() || null,
              deductible: f.deductible ? num(f.deductible) : "0.00",
            }
          : {
              ledger_id: ledgerId,
              title: (f.title ?? "").trim(),
              cost_frame: num(f.costFrame ?? ""),
              kind: f.kind,
              kind_basis: f.kindBasis?.trim() || null,
            };
    const path = kind === "loan" ? "loans" : kind === "claim" ? "insurance-claims" : "measures";
    const res = await call<{ id: string }>(path, body);
    if (res) router.push(`${basePath}/${kind === "loan" ? "darlehen" : kind === "claim" ? "versicherung" : "massnahme"}/${res.id}`);
  };
  return (
    <div className="flex flex-col gap-1" data-testid={`finance-create-${kind}`}>
      <div className="flex flex-wrap items-end gap-2">
        {kind === "loan" ? (
          <>
            <Field label={t("lender")}>
              <input className={ui.input} value={f.lender ?? ""} onChange={set("lender")} />
            </Field>
            <Field label={t("principal")}>
              <input className={ui.input} inputMode="decimal" value={f.principal ?? ""} onChange={set("principal")} />
            </Field>
            <Field label={t("rate")}>
              <input className={ui.input} inputMode="decimal" value={f.rate ?? ""} onChange={set("rate")} />
            </Field>
            <Field label={t("termMonths")}>
              <input className={ui.input} type="number" min={1} value={f.term ?? ""} onChange={set("term")} />
            </Field>
            <Field label={t("instalment")}>
              <input className={ui.input} inputMode="decimal" value={f.instalment ?? ""} onChange={set("instalment")} />
            </Field>
            <Field label={t("startDate")}>
              <input className={ui.input} type="date" value={f.start ?? ""} onChange={set("start")} />
            </Field>
            <Field label={t("purpose")}>
              <input className={ui.input} value={f.purpose ?? ""} onChange={set("purpose")} />
            </Field>
            <Field label={t("loanAccount")}>
              <select className={ui.input} value={f.account} onChange={set("account")}>
                <option value="">·</option>
                {loanAccounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.number} {a.name}
                  </option>
                ))}
              </select>
            </Field>
          </>
        ) : null}
        {kind === "claim" ? (
          <>
            <Field label={t("title")}>
              <input className={ui.input} value={f.title ?? ""} onChange={set("title")} />
            </Field>
            <Field label={t("damageDate")}>
              <input className={ui.input} type="date" value={f.damageDate ?? ""} onChange={set("damageDate")} />
            </Field>
            <Field label={t("insurer")}>
              <input className={ui.input} value={f.insurer ?? ""} onChange={set("insurer")} />
            </Field>
            <Field label={t("policy")}>
              <input className={ui.input} value={f.policy ?? ""} onChange={set("policy")} />
            </Field>
            <Field label={t("deductible")}>
              <input className={ui.input} inputMode="decimal" value={f.deductible ?? ""} onChange={set("deductible")} />
            </Field>
          </>
        ) : null}
        {kind === "measure" ? (
          <>
            <Field label={t("title")}>
              <input className={ui.input} value={f.title ?? ""} onChange={set("title")} />
            </Field>
            <Field label={t("costFrame")}>
              <input className={ui.input} inputMode="decimal" value={f.costFrame ?? ""} onChange={set("costFrame")} />
            </Field>
            <Field label={t("kind")}>
              <select className={ui.input} value={f.kind} onChange={set("kind")}>
                {(["undecided", "maintenance", "structural_change"] as const).map((k) => (
                  <option key={k} value={k}>
                    {t(`kinds.${k}`)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("kindBasis")}>
              <input className={ui.input} value={f.kindBasis ?? ""} onChange={set("kindBasis")} />
            </Field>
          </>
        ) : null}
        <button type="button" className={ui.button} disabled={busy || !valid} onClick={create}>
          {t(`create.${kind}`)}
        </button>
      </div>
      <ErrorLine error={error} />
    </div>
  );
}

/** Loan or claim item with optional journal entry reference (the entry makes it a fact). */
export function ItemForm({ target, id, kinds }: { target: "loans" | "insurance-claims"; id: string; kinds: string[] }) {
  const t = useTranslations("HoaFinance");
  const { busy, error, call } = useCall();
  const [kind, setKind] = useState(kinds[0] ?? "");
  const [day, setDay] = useState("");
  const [amount, setAmount] = useState("");
  const [entry, setEntry] = useState("");
  const [contract, setContract] = useState("");
  const [note, setNote] = useState("");
  const group = target === "loans" ? "loanKinds" : "claimKinds";
  const valid = !!kind && !!day && MONEY.test(amount) && !amount.startsWith("-") && (kind !== "owner_payment" || contract.trim().length > 0);
  const add = async () => {
    const res = await call(`${target}/${id}/items`, {
      kind,
      booking_date: day,
      amount: num(amount),
      journal_entry_id: entry.trim() || null,
      note: note.trim() || null,
      ...(kind === "owner_payment" ? { contract_id: contract.trim() } : {}),
    });
    if (res !== null) {
      setAmount("");
      setEntry("");
      setNote("");
    }
  };
  return (
    <div className="flex flex-col gap-1" data-testid="finance-item-form">
      <div className="flex flex-wrap items-end gap-2">
        <Field label={t("itemKind")}>
          <select className={ui.input} value={kind} onChange={(e) => setKind(e.target.value)}>
            {kinds.map((k) => (
              <option key={k} value={k}>
                {t(`${group}.${k}`)}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("bookingDate")}>
          <input className={ui.input} type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        </Field>
        <Field label={t("amount")}>
          <input className={ui.input} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        <Field label={t("journalEntry")}>
          <input className={ui.input} value={entry} onChange={(e) => setEntry(e.target.value)} />
        </Field>
        {kind === "owner_payment" ? (
          <Field label={t("contract")}>
            <input className={ui.input} value={contract} onChange={(e) => setContract(e.target.value)} />
          </Field>
        ) : null}
        <Field label={t("note")}>
          <input className={ui.input} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <button type="button" className={ui.button} disabled={busy || !valid} onClick={add}>
          {t("addItem")}
        </button>
      </div>
      <ErrorLine error={error} />
    </div>
  );
}

/** Financing share of a measure (reserve, special levy, loan, other). */
export function FinancingForm({ measureId }: { measureId: string }) {
  const t = useTranslations("HoaFinance");
  const { busy, error, call } = useCall();
  const [source, setSource] = useState("reserve");
  const [amount, setAmount] = useState("");
  const [ref, setRef] = useState("");
  const needsRef = source === "special_levy" || source === "loan";
  const valid = MONEY.test(amount) && !amount.startsWith("-") && (!needsRef || ref.trim().length > 0);
  const add = async () => {
    const res = await call(`measures/${measureId}/financing`, {
      source,
      amount: num(amount),
      ...(source === "special_levy" ? { special_levy_id: ref.trim() } : {}),
      ...(source === "loan" ? { loan_id: ref.trim() } : {}),
    });
    if (res !== null) {
      setAmount("");
      setRef("");
    }
  };
  return (
    <div className="flex flex-col gap-1" data-testid="financing-form">
      <div className="flex flex-wrap items-end gap-2">
        <Field label={t("source")}>
          <select className={ui.input} value={source} onChange={(e) => setSource(e.target.value)}>
            {(["reserve", "special_levy", "loan", "other"] as const).map((s) => (
              <option key={s} value={s}>
                {t(`sources.${s}`)}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("amount")}>
          <input className={ui.input} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        {needsRef ? (
          <Field label={t("reference")}>
            <input className={ui.input} value={ref} onChange={(e) => setRef(e.target.value)} />
          </Field>
        ) : null}
        <button type="button" className={ui.button} disabled={busy || !valid} onClick={add}>
          {t("addFinancing")}
        </button>
      </div>
      <ErrorLine error={error} />
    </div>
  );
}

/** Status of a measure or claim (PATCH). */
export function StatusSelect({ target, id, status, options, group }: { target: "measures" | "insurance-claims"; id: string; status: string; options: string[]; group: "measureStatus" | "claimStatus" }) {
  const t = useTranslations("HoaFinance");
  const { busy, error, call } = useCall();
  const [value, setValue] = useState(status);
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-end gap-2">
        <Field label={t("status")}>
          <select className={ui.input} value={value} onChange={(e) => setValue(e.target.value)}>
            {options.map((o) => (
              <option key={o} value={o}>
                {t(`${group}.${o}`)}
              </option>
            ))}
          </select>
        </Field>
        <button type="button" className={ui.button} disabled={busy || value === status} onClick={() => call(`${target}/${id}`, { status: value }, "PATCH")}>
          {t("setStatus")}
        </button>
      </div>
      <ErrorLine error={error} />
    </div>
  );
}

type Note = { code: string; amount: string; note: string };
const NOTE_CODES = ["heating_accrual", "creditor_timing", "prior_year", "other"] as const;

/** Explained differences of the cash flow reconciliation (W04); only before the internal approval. */
export function ReconciliationNotes({ statementId, notes }: { statementId: string; notes: Note[] }) {
  const t = useTranslations("HoaFinance");
  const { busy, error, call } = useCall();
  const [rows, setRows] = useState<Note[]>(notes);
  const update = (i: number, k: keyof Note, v: string) => setRows((r) => r.map((n, j) => (j === i ? { ...n, [k]: v } : n)));
  const valid = rows.every((n) => MONEY.test(n.amount) && n.note.trim().length >= 3);
  return (
    <div className="flex flex-col gap-2" data-testid="reconciliation-notes">
      <h3 className={ui.h2}>{t("notes")}</h3>
      {rows.map((n, i) => (
        <div key={i} className="flex flex-wrap items-end gap-2">
          <Field label={t("noteCode")}>
            <select className={ui.input} value={n.code} onChange={(e) => update(i, "code", e.target.value)}>
              {NOTE_CODES.map((c) => (
                <option key={c} value={c}>
                  {t(`bridge.${c}`)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("noteAmount")}>
            <input className={ui.input} inputMode="decimal" value={n.amount} onChange={(e) => update(i, "amount", e.target.value)} />
          </Field>
          <Field label={t("noteText")}>
            <input className={ui.input} value={n.note} onChange={(e) => update(i, "note", e.target.value)} />
          </Field>
          <button type="button" className={ui.buttonSm} onClick={() => setRows((r) => r.filter((_, j) => j !== i))}>
            {t("removeNote")}
          </button>
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        <button type="button" className={ui.buttonSm} onClick={() => setRows((r) => [...r, { code: "heating_accrual", amount: "", note: "" }])}>
          {t("addNote")}
        </button>
        <button
          type="button"
          className={ui.button}
          disabled={busy || !valid}
          onClick={() =>
            call(`statements/${statementId}/reconciliation-notes`, { notes: rows.map((n) => ({ code: n.code, amount: num(n.amount), note: n.note.trim() })) }, "PUT")
          }
        >
          {t("saveNotes")}
        </button>
      </div>
      <ErrorLine error={error} />
    </div>
  );
}
