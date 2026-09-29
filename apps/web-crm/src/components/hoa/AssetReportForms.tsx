"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** M24-02 asset report (W11) and M24-03 loans in the statement: create, calculate, manual
 *  items, issue (G4) and the loan display configuration. Everything is recording; nothing
 *  posts and nothing is issued to owners before gate G4. */

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
    const res = await bff<T>(`/api/bff/hoa/${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) });
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className={ui.label}>{label}</span>
      {children}
    </label>
  );
}

function Lines({ error, saved, busy }: { error: string | null; saved: boolean; busy: boolean }) {
  const t = useTranslations("HoaFinance");
  return (
    <>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {busy ? <p className={ui.help}>{t("saving")}</p> : null}
      {saved && !busy ? (
        <p role="status" className={ui.success}>
          {t("saved")}
        </p>
      ) : null}
    </>
  );
}

/** Creates an asset report draft for the community ledger and opens it. */
export function AssetReportCreate({ ledgerId, basePath }: { ledgerId: string; basePath: string }) {
  const t = useTranslations("HoaFinance");
  const { busy, error, call, router } = useCall();
  const [asOf, setAsOf] = useState("");
  const [opening, setOpening] = useState("0,00");
  const [withdrawals, setWithdrawals] = useState("0,00");
  const [interest, setInterest] = useState("0,00");
  const valid = asOf !== "" && [opening, withdrawals, interest].every((v) => MONEY.test(v));
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const created = await call<{ id: string }>("asset-reports", {
      ledger_id: ledgerId,
      as_of: asOf,
      reserve_opening: num(opening),
      reserve_withdrawals: num(withdrawals),
      reserve_interest: num(interest),
    });
    if (created) router.push(`${basePath}/vermoegensbericht/${created.id}`);
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-2 rounded border border-border p-3" data-testid="asset-report-create">
      <Field label={t("asOf")}>
        <input type="date" className={ui.input} value={asOf} onChange={(e) => setAsOf(e.target.value)} required />
      </Field>
      <Field label={t("reserveOpening")}>
        <input className={ui.input} value={opening} onChange={(e) => setOpening(e.target.value)} inputMode="decimal" />
      </Field>
      <Field label={t("reserveWithdrawals")}>
        <input className={ui.input} value={withdrawals} onChange={(e) => setWithdrawals(e.target.value)} inputMode="decimal" />
      </Field>
      <Field label={t("reserveInterest")}>
        <input className={ui.input} value={interest} onChange={(e) => setInterest(e.target.value)} inputMode="decimal" />
      </Field>
      <div className={ui.formActions}>
        <button type="submit" className={ui.primary} disabled={busy || !valid}>
          {t("assetReportCreate")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </form>
  );
}

export type ManualItem = { label: string; amount: string; note: string | null };

/** Calculate, issue (G4) and the manual items of other community assets. */
export function AssetReportActions({ id, status, manualItems }: { id: string; status: string; manualItems: ManualItem[] }) {
  const t = useTranslations("HoaFinance");
  const { busy, error, saved, call } = useCall();
  const [items, setItems] = useState<ManualItem[]>(manualItems);
  const editable = status !== "issued";
  const itemsValid = items.every((i) => i.label.trim() !== "" && MONEY.test(i.amount));
  const update = (index: number, patch: Partial<ManualItem>) => setItems(items.map((i, n) => (n === index ? { ...i, ...patch } : i)));
  return (
    <section className="flex flex-col gap-3" data-testid="asset-report-actions">
      <div className={ui.formActions}>
        {editable ? (
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void call(`asset-reports/${id}/calculate`, undefined)}>
            {t("calculate")}
          </button>
        ) : null}
        {status === "calculated" ? (
          <button type="button" className={ui.secondary} disabled={busy} onClick={() => void call(`asset-reports/${id}/transition`, { target: "issued" })}>
            {t("issue")}
          </button>
        ) : null}
        {status !== "draft" ? (
          <a className={ui.secondary} href={`/api/bff/hoa/asset-reports/${id}/pdf`}>
            {t("pdfDraft")}
          </a>
        ) : null}
      </div>
      {editable ? (
        <form
          className="flex flex-col gap-2 rounded border border-border p-3"
          data-testid="manual-items"
          onSubmit={(e) => {
            e.preventDefault();
            void call(
              `asset-reports/${id}`,
              { manual_items: items.map((i) => ({ label: i.label.trim(), amount: num(i.amount), note: i.note?.trim() || null })) },
              "PATCH",
            );
          }}
        >
          <h3 className="font-medium">{t("manualBlock")}</h3>
          {items.map((item, index) => (
            <div key={index} className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <Field label={t("manualLabel")}>
                <input className={ui.input} value={item.label} onChange={(e) => update(index, { label: e.target.value })} />
              </Field>
              <Field label={t("manualAmount")}>
                <input className={ui.input} value={item.amount} onChange={(e) => update(index, { amount: e.target.value })} inputMode="decimal" />
              </Field>
              <Field label={t("manualNote")}>
                <input className={ui.input} value={item.note ?? ""} onChange={(e) => update(index, { note: e.target.value })} />
              </Field>
            </div>
          ))}
          <div className={ui.formActions}>
            <button type="button" className={ui.secondary} onClick={() => setItems([...items, { label: "", amount: "", note: "" }])}>
              {t("manualAdd")}
            </button>
            <button type="submit" className={ui.primary} disabled={busy || !itemsValid}>
              {t("manualSave")}
            </button>
          </div>
        </form>
      ) : null}
      <Lines error={error} saved={saved} busy={busy} />
    </section>
  );
}

export type LoanOption = { id: string; label: string };
export type KeyOption = { id: string; code: string; name: string };
export type LoanAllocationRow = { loan_id: string; allocation_key_id: string; components: string[]; basis: string };

/** M24-03: which loans the statement shows per unit, by which key and on which basis. The
 *  shares are information only and never enter the result. */
export function LoanAllocationForm({ statementId, loans, keys, current }: { statementId: string; loans: LoanOption[]; keys: KeyOption[]; current: LoanAllocationRow[] }) {
  const t = useTranslations("HoaFinance");
  const { busy, error, saved, call } = useCall();
  const [rows, setRows] = useState<LoanAllocationRow[]>(current);
  const update = (index: number, patch: Partial<LoanAllocationRow>) => setRows(rows.map((r, n) => (n === index ? { ...r, ...patch } : r)));
  const valid = rows.every((r) => r.loan_id && r.allocation_key_id && r.basis.trim().length >= 5 && r.components.length > 0);
  const toggle = (index: number, component: string, on: boolean) => {
    const row = rows[index];
    if (!row) return;
    const components = on ? Array.from(new Set([...row.components, component])) : row.components.filter((c) => c !== component);
    update(index, { components });
  };
  return (
    <form
      className="flex flex-col gap-2 rounded border border-border p-3"
      data-testid="loan-allocation"
      onSubmit={(e) => {
        e.preventDefault();
        void call(`statements/${statementId}/loan-allocation`, { loans: rows.map((r) => ({ ...r, basis: r.basis.trim() })) }, "PUT");
      }}
    >
      <h3 className="font-medium">{t("loanAllocation")}</h3>
      <p className={ui.help}>{t("loanAllocationNote")}</p>
      {rows.map((row, index) => (
        <div key={index} className="grid grid-cols-1 gap-2 sm:grid-cols-4">
          <Field label={t("loanAllocationLoan")}>
            <select className={ui.input} value={row.loan_id} onChange={(e) => update(index, { loan_id: e.target.value })}>
              <option value="">·</option>
              {loans.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("loanAllocationKey")}>
            <select className={ui.input} value={row.allocation_key_id} onChange={(e) => update(index, { allocation_key_id: e.target.value })}>
              <option value="">·</option>
              {keys.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.code} {k.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("loanAllocationBasis")}>
            <input className={ui.input} value={row.basis} onChange={(e) => update(index, { basis: e.target.value })} />
          </Field>
          <fieldset className="flex flex-col gap-1">
            <legend className={ui.label}>{t("loanAllocationComponents")}</legend>
            {(["interest", "repayment"] as const).map((c) => (
              <label key={c} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={row.components.includes(c)} onChange={(e) => toggle(index, c, e.target.checked)} />
                {t(`components.${c}`)}
              </label>
            ))}
          </fieldset>
        </div>
      ))}
      <div className={ui.formActions}>
        <button type="button" className={ui.secondary} onClick={() => setRows([...rows, { loan_id: "", allocation_key_id: "", components: ["interest", "repayment"], basis: "" }])}>
          {t("manualAdd")}
        </button>
        <button type="submit" className={ui.primary} disabled={busy || !valid}>
          {t("loanAllocationSave")}
        </button>
      </div>
      <Lines error={error} saved={saved} busy={busy} />
    </form>
  );
}
