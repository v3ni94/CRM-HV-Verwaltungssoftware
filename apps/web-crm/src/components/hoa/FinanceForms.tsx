"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** W10 (A59) and W04 (A60) forms: loans, insurance claims, measures and the explained
 *  differences of the cash flow reconciliation. Everything is recording; nothing posts. */

type Account = { id: string; number: string; name: string };
export type ResolutionOption = { id: string; number?: number | null; decided_on: string; subject: string };
const resolutionLabel = (r: ResolutionOption) => `${r.number ? `Nr. ${r.number} · ` : ""}${r.decided_on} · ${r.subject}`;
const MONEY = /^-?\d+([.,]\d{1,2})?$/;
const num = (v: string) => v.replace(",", ".");

function useCall() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const call = async <T,>(path: string, body: unknown, method = "POST"): Promise<T | null> => {
    setBusy(true);
    setError(null);
    setSaved(false);
    const res = await bff<T>(`/api/bff/hoa/${path}`, { method, body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return null;
    }
    setSaved(true);
    router.refresh();
    return res.data;
  };
  return { busy, error, saved, call, router };
}

/** Validation hint under a form: which fields are missing or malformed (the button stays
 *  disabled until the hint disappears). */
function Hint({ text }: { text: string | null }) {
  return text ? <p className={ui.help}>{text}</p> : null;
}

function StatusLine({ saved, busy }: { saved: boolean; busy: boolean }) {
  const t = useTranslations("HoaFinance");
  if (busy) return <p className={ui.help}>{t("saving")}</p>;
  return saved ? (
    <p role="status" className={ui.success}>
      {t("saved")}
    </p>
  ) : null;
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
  resolutions = [],
}: {
  kind: "loan" | "claim" | "measure";
  ledgerId: string;
  basePath: string;
  loanAccounts?: Account[];
  /** A79: resolutions of the same community, offered for the claim. */
  resolutions?: ResolutionOption[];
}) {
  const t = useTranslations("HoaFinance");
  const { busy, error, call, router } = useCall();
  const [f, setF] = useState<Record<string, string>>({ kind: "undecided", account: "", resolution: "" });
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF((s) => ({ ...s, [k]: e.target.value }));
  const missing: string[] = [];
  const malformed: string[] = [];
  const need = (ok: boolean, label: string) => (ok ? undefined : missing.push(label));
  const number = (v: string | undefined, label: string) => (v && !MONEY.test(v) ? malformed.push(label) : undefined);
  if (kind === "loan") {
    need((f.lender ?? "").trim().length >= 2, t("lender"));
    need(MONEY.test(f.principal ?? ""), t("principal"));
    need(MONEY.test(f.rate ?? ""), t("rate"));
    need(!!f.start, t("startDate"));
    need((f.purpose ?? "").trim().length >= 3, t("purpose"));
    number(f.principal, t("principal"));
    number(f.rate, t("rate"));
    number(f.instalment, t("instalment"));
  } else if (kind === "claim") {
    need((f.title ?? "").trim().length >= 3, t("title"));
    need(!!f.damageDate, t("damageDate"));
    number(f.deductible, t("deductible"));
  } else {
    need((f.title ?? "").trim().length >= 3, t("title"));
    need(MONEY.test(f.costFrame ?? ""), t("costFrame"));
    need(f.kind === "undecided" || (f.kindBasis ?? "").trim().length >= 3, t("kindBasis"));
    number(f.costFrame, t("costFrame"));
  }
  const valid = missing.length === 0 && malformed.length === 0;
  const hint = malformed.length ? `${t("invalidNumber")} (${malformed.join(", ")})` : missing.length ? t("missingFields", { fields: missing.join(", ") }) : null;
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
              resolution_id: f.resolution || null,
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
            {resolutions.length > 0 ? (
              <Field label={t("resolution")}>
                <select className={ui.input} value={f.resolution} onChange={set("resolution")}>
                  <option value="">{t("noResolution")}</option>
                  {resolutions.map((r) => (
                    <option key={r.id} value={r.id}>
                      {resolutionLabel(r)}
                    </option>
                  ))}
                </select>
              </Field>
            ) : null}
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
        <button type="button" className={ui.primary} disabled={busy || !valid} onClick={create}>
          {t(`create.${kind}`)}
        </button>
      </div>
      <Hint text={hint} />
      {busy ? <p className={ui.help}>{t("saving")}</p> : null}
      <ErrorLine error={error} />
    </div>
  );
}

/** Loan or claim item with optional journal entry reference (the entry makes it a fact). */
export function ItemForm({ target, id, kinds }: { target: "loans" | "insurance-claims"; id: string; kinds: string[] }) {
  const t = useTranslations("HoaFinance");
  const { busy, error, saved, call } = useCall();
  const dayRef = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState(kinds[0] ?? "");
  const [day, setDay] = useState("");
  const [amount, setAmount] = useState("");
  const [entry, setEntry] = useState("");
  const [contract, setContract] = useState("");
  const [note, setNote] = useState("");
  const group = target === "loans" ? "loanKinds" : "claimKinds";
  const amountValid = MONEY.test(amount) && !amount.startsWith("-");
  const missing = [
    ...(day ? [] : [t("bookingDate")]),
    ...(amount ? [] : [t("amount")]),
    ...(kind === "owner_payment" && contract.trim().length === 0 ? [t("contract")] : []),
  ];
  const valid = !!kind && amountValid && missing.length === 0;
  const hint = amount && !amountValid ? t("invalidAmount") : missing.length ? t("missingFields", { fields: missing.join(", ") }) : null;
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
      dayRef.current?.focus();
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
          <input ref={dayRef} className={ui.input} type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        </Field>
        <Field label={t("amount")}>
          <input className={ui.input} inputMode="decimal" value={amount} aria-invalid={!!amount && !amountValid} onChange={(e) => setAmount(e.target.value)} />
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
        <button type="button" className={ui.primary} disabled={busy || !valid} onClick={add}>
          {t("addItem")}
        </button>
      </div>
      <Hint text={hint} />
      <StatusLine saved={saved} busy={busy} />
      <ErrorLine error={error} />
    </div>
  );
}

/** Financing share of a measure (reserve, special levy, loan, other). */
export function FinancingForm({ measureId }: { measureId: string }) {
  const t = useTranslations("HoaFinance");
  const { busy, error, saved, call } = useCall();
  const amountRef = useRef<HTMLInputElement>(null);
  const [source, setSource] = useState("reserve");
  const [amount, setAmount] = useState("");
  const [ref, setRef] = useState("");
  const needsRef = source === "special_levy" || source === "loan";
  const amountValid = MONEY.test(amount) && !amount.startsWith("-");
  const valid = amountValid && (!needsRef || ref.trim().length > 0);
  const hint = amount && !amountValid ? t("invalidAmount") : !amount ? t("missingFields", { fields: t("amount") }) : needsRef && ref.trim().length === 0 ? t("missingFields", { fields: t("reference") }) : null;
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
      amountRef.current?.focus();
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
          <input ref={amountRef} className={ui.input} inputMode="decimal" value={amount} aria-invalid={!!amount && !amountValid} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        {needsRef ? (
          <Field label={t("reference")}>
            <input className={ui.input} value={ref} onChange={(e) => setRef(e.target.value)} />
          </Field>
        ) : null}
        <button type="button" className={ui.primary} disabled={busy || !valid} onClick={add}>
          {t("addFinancing")}
        </button>
      </div>
      <Hint text={hint} />
      <StatusLine saved={saved} busy={busy} />
      <ErrorLine error={error} />
    </div>
  );
}

/** Status of a measure or claim (PATCH). */
export function StatusSelect({ target, id, status, options, group }: { target: "measures" | "insurance-claims"; id: string; status: string; options: string[]; group: "measureStatus" | "claimStatus" }) {
  const t = useTranslations("HoaFinance");
  const { busy, error, saved, call } = useCall();
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
        <button type="button" className={ui.primary} disabled={busy || value === status} onClick={() => call(`${target}/${id}`, { status: value }, "PATCH")}>
          {t("setStatus")}
        </button>
      </div>
      <StatusLine saved={saved} busy={busy} />
      <ErrorLine error={error} />
    </div>
  );
}

/** A79: structured resolution link of an insurance claim (PATCH resolution_id), checked
 *  server side against the resolutions of the same community. */
export function ResolutionSelect({ claimId, resolutionId, resolutions }: { claimId: string; resolutionId: string | null; resolutions: ResolutionOption[] }) {
  const t = useTranslations("HoaFinance");
  const { busy, error, call } = useCall();
  const [value, setValue] = useState(resolutionId ?? "");
  return (
    <div className="flex flex-col gap-1" data-testid="claim-resolution">
      <div className="flex flex-wrap items-end gap-2">
        <Field label={t("resolution")}>
          <select className={ui.input} value={value} onChange={(e) => setValue(e.target.value)}>
            <option value="">{t("noResolution")}</option>
            {resolutions.map((r) => (
              <option key={r.id} value={r.id}>
                {resolutionLabel(r)}
              </option>
            ))}
          </select>
        </Field>
        <button
          type="button"
          className={ui.button}
          disabled={busy || value === (resolutionId ?? "") || value === ""}
          onClick={() => call(`insurance-claims/${claimId}`, { resolution_id: value }, "PATCH")}
        >
          {t("setResolution")}
        </button>
      </div>
      <ErrorLine error={error} />
    </div>
  );
}

type Note = { code: string; amount: string; note: string };
const NOTE_CODES = ["heating_accrual", "creditor_timing", "prior_year", "migration_opening", "other"] as const;

/** Explained differences of the cash flow reconciliation (W04); only before the internal approval. */
export function ReconciliationNotes({ statementId, notes }: { statementId: string; notes: Note[] }) {
  const t = useTranslations("HoaFinance");
  const { busy, error, saved, call } = useCall();
  const [rows, setRows] = useState<Note[]>(notes);
  const update = (i: number, k: keyof Note, v: string) => setRows((r) => r.map((n, j) => (j === i ? { ...n, [k]: v } : n)));
  const valid = rows.every((n) => MONEY.test(n.amount) && n.note.trim().length >= 3);
  const hint = valid ? null : rows.some((n) => n.amount && !MONEY.test(n.amount)) ? t("invalidNumber") : t("missingFields", { fields: `${t("noteAmount")}, ${t("noteText")}` });
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
      <Hint text={hint} />
      <StatusLine saved={saved} busy={busy} />
      <ErrorLine error={error} />
    </div>
  );
}
