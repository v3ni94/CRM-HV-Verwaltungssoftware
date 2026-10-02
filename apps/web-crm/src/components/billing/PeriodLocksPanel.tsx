"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Lock = { id: string; period_from: string; period_to: string; source: string; reason: string | null; active: boolean };
type StatementLock = { locks: Lock[]; auto_lock_on_close: boolean; lock_mode: string };

/** GAF-13, GAG-11: period locks of the property of a statement (GET accounting/period-locks),
 *  the lock created when this statement was closed (GET statements/{id}/period-lock) and setting
 *  a lock for the statement period (POST accounting/period-locks, approve permission checked by
 *  the API). Releasing a lock stays in the accounting module (four eyes). */
export function PeriodLocksPanel({
  propertyId,
  statementId,
  ledgerId,
  periodFrom,
  periodTo,
}: {
  propertyId: string;
  statementId?: string;
  ledgerId?: string;
  periodFrom?: string;
  periodTo?: string;
}) {
  const t = useTranslations("BillingExtra.periodLocks");
  const [locks, setLocks] = useState<Lock[] | null>(null);
  const [stLock, setStLock] = useState<StatementLock | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState(false);

  const load = useCallback(async () => {
    const res = await bff<Lock[]>(`/api/bff/accounting/period-locks?property_id=${propertyId}&active=true`);
    if (res.ok) setLocks(res.data ?? []);
    else setError(res.message);
    if (statementId) {
      const s = await bff<StatementLock>(`/api/bff/statements/${statementId}/period-lock`);
      if (s.ok && s.data && Array.isArray(s.data.locks)) setStLock(s.data);
    }
  }, [propertyId, statementId]);

  useEffect(() => {
    void load();
  }, [load]);

  const canCreate = Boolean(ledgerId && periodFrom && periodTo);
  const create = async () => {
    setBusy(true);
    setError(null);
    setCreated(false);
    const res = await bff("/api/bff/accounting/period-locks", {
      method: "POST",
      body: JSON.stringify({
        ledger_id: ledgerId,
        property_id: propertyId,
        period_from: periodFrom,
        period_to: periodTo,
        reason: reason.trim(),
      }),
    });
    setBusy(false);
    if (res.ok) {
      setReason("");
      setCreated(true);
      await load();
    } else setError(res.message);
  };

  return (
    <section className="flex flex-col gap-2" data-testid="period-locks">
      <h3 className={ui.h2}>{t("title")}</h3>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {locks && locks.length === 0 ? <p className={ui.help}>{t("none")}</p> : null}
      {locks && locks.length > 0 ? (
        <ul className="flex flex-col gap-1 text-sm">
          {locks.map((l) => (
            <li key={l.id}>
              {formatDate(l.period_from)} {t("until")} {formatDate(l.period_to)}{l.reason ? `, ${l.reason}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
      {stLock ? (
        <p className={ui.help} data-testid="statement-period-lock">
          {stLock.locks.some((l) => l.active)
            ? t("statementLocked")
            : t("statementNotLocked")}{" "}
          {stLock.auto_lock_on_close ? t("autoOn", { mode: stLock.lock_mode }) : t("autoOff")}
        </p>
      ) : null}
      {canCreate ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("reason")}</span>
            <input className={ui.input} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <button type="button" className={ui.button} onClick={create} disabled={busy || reason.trim().length < 3}>
            {t("create", { from: formatDate(periodFrom ?? ""), to: formatDate(periodTo ?? "") })}
          </button>
        </div>
      ) : null}
      {created ? <p className={ui.help} role="status">{t("created")}</p> : null}
      <p className={ui.help}>{t("hint")}</p>
    </section>
  );
}
