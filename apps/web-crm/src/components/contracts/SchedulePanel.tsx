"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import type { AmountBasis, DueDayRule, PaymentInterval, PaymentMode, ScheduleOut } from "./ContractForm";

const INTERVALS: PaymentInterval[] = ["monthly", "quarterly", "semiannual", "annual"];
const DUE_DAY_RULES: DueDayRule[] = ["day", "workday", "last_day", "day_next_month"];
const PAYMENT_MODES: PaymentMode[] = ["advance", "arrears"];
const AMOUNT_BASES: AmountBasis[] = ["per_month", "per_instalment"];

/** GAJ-102 (6.3): payment plans of the contract with a correction form (PATCH schedules/{id}).
 *  The API refuses changes once a posted receivable uses the plan (409); its message is shown
 *  unchanged. Correcting a plan posts nothing. */
export function SchedulePanel({ contractId, schedules, canUpdate }: { contractId: string; schedules: ScheduleOut[]; canUpdate: boolean }) {
  const t = useTranslations("ContractForm");
  const [rows, setRows] = useState(schedules);
  const [editingId, setEditingId] = useState<string | null>(null);
  return (
    <section className={ui.card} data-testid="contract-schedules">
      <h2 className={ui.h2}>{t("page.schedules")}</h2>
      {rows.length === 0 ? (
        <p className={ui.help}>{t("schedule.none")}</p>
      ) : (
        <ul className="text-sm">
          {rows.map((s) => (
            <li key={s.id} className="py-1" data-testid="schedule-row">
              {t(`intervals.${s.interval}`)}, {t(`dueDayRules.${s.due_day_rule}`)} {s.due_day}, {t("schedule.from")} {formatDate(s.valid_from)}
              {s.valid_to ? ` ${t("schedule.to")} ${formatDate(s.valid_to)}` : ""}
              {canUpdate ? (
                <button type="button" className={`${ui.buttonSm} ml-2`} onClick={() => setEditingId(editingId === s.id ? null : s.id)}>
                  {t("scheduleEdit.open")}
                </button>
              ) : null}
              {editingId === s.id ? (
                <ScheduleCorrectionForm
                  contractId={contractId}
                  row={s}
                  onCancel={() => setEditingId(null)}
                  onSaved={(updated) => {
                    setRows((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
                    setEditingId(null);
                  }}
                />
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function ScheduleCorrectionForm({ contractId, row, onSaved, onCancel }: { contractId: string; row: ScheduleOut; onSaved: (row: ScheduleOut) => void; onCancel: () => void }) {
  const t = useTranslations("ContractForm");
  const router = useRouter();
  const [interval, setInterval] = useState<PaymentInterval>(row.interval);
  const [rule, setRule] = useState<DueDayRule>(row.due_day_rule);
  const [dueDay, setDueDay] = useState(String(row.due_day));
  const [validFrom, setValidFrom] = useState(row.valid_from);
  const [validTo, setValidTo] = useState(row.valid_to ?? "");
  const [mode, setMode] = useState<PaymentMode>(row.payment_mode ?? "advance");
  const [basis, setBasis] = useState<AmountBasis>(row.amount_basis ?? "per_month");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const day = Number(dueDay);
  const valid = Number.isInteger(day) && day >= 1 && day <= 31 && validFrom !== "" && (validTo === "" || validTo >= validFrom);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    const res = await bff<ScheduleOut>(`/api/bff/contracts/${contractId}/schedules/${row.id}`, {
      method: "PATCH",
      body: JSON.stringify({ interval, due_day_rule: rule, due_day: day, valid_from: validFrom, valid_to: validTo || null, payment_mode: mode, amount_basis: basis }),
    });
    setBusy(false);
    if (res.ok) {
      onSaved(res.data);
      router.refresh();
    } else setError(res.message);
  }

  return (
    <form onSubmit={save} className="mt-2 grid gap-3 sm:grid-cols-4" aria-label={t("scheduleEdit.title")} data-testid="schedule-correction-form" noValidate>
      <p className={`${ui.help} sm:col-span-4`}>{t("scheduleEdit.help")}</p>
      <label className={ui.label}>
        {t("schedule.interval")}
        <select className={ui.input} value={interval} onChange={(e) => setInterval(e.target.value as PaymentInterval)}>
          {INTERVALS.map((i) => (
            <option key={i} value={i}>
              {t(`intervals.${i}`)}
            </option>
          ))}
        </select>
      </label>
      <label className={ui.label}>
        {t("schedule.dueDayRule")}
        <select className={ui.input} value={rule} onChange={(e) => setRule(e.target.value as DueDayRule)}>
          {DUE_DAY_RULES.map((r) => (
            <option key={r} value={r}>
              {t(`dueDayRules.${r}`)}
            </option>
          ))}
        </select>
      </label>
      <label className={ui.label}>
        {t("schedule.dueDay")}
        <input className={ui.input} inputMode="numeric" value={dueDay} onChange={(e) => setDueDay(e.target.value)} />
      </label>
      <label className={ui.label}>
        {t("schedule.paymentMode")}
        <select className={ui.input} value={mode} onChange={(e) => setMode(e.target.value as PaymentMode)}>
          {PAYMENT_MODES.map((m) => (
            <option key={m} value={m}>
              {t(`paymentModes.${m}`)}
            </option>
          ))}
        </select>
      </label>
      <label className={ui.label}>
        {t("schedule.amountBasis")}
        <select className={ui.input} value={basis} onChange={(e) => setBasis(e.target.value as AmountBasis)}>
          {AMOUNT_BASES.map((b) => (
            <option key={b} value={b}>
              {t(`amountBases.${b}`)}
            </option>
          ))}
        </select>
      </label>
      <label className={ui.label}>
        {t("schedule.validFrom")}
        <input className={ui.input} type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
      </label>
      <label className={ui.label}>
        {t("schedule.validTo")}
        <input className={ui.input} type="date" value={validTo} onChange={(e) => setValidTo(e.target.value)} />
      </label>
      <div className="flex items-end gap-2">
        <button type="submit" className={ui.primary} disabled={busy || !valid}>
          {t("scheduleEdit.save")}
        </button>
        <button type="button" className={ui.button} onClick={onCancel} disabled={busy}>
          {t("scheduleEdit.cancel")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={`${ui.alert} sm:col-span-4`}>
          {error}
        </p>
      ) : null}
    </form>
  );
}
