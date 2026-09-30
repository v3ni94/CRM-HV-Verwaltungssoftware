"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type LockResult = { locked_until: string; drafts_in_locked_period: number; unclarified_bank_movements: number };

/** Festschreiben bis Datum (M10-02, B05). Irreversible, therefore confirmed. */
export function LedgerLockForm({ ledgerId, lockedUntil }: { ledgerId: string; lockedUntil: string | null }) {
  const t = useTranslations("Bookkeeping");
  const router = useRouter();
  const [until, setUntil] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LockResult | null>(null);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!window.confirm(t("lock.confirm", { date: formatDate(until) }))) return;
    setBusy(true);
    setError(null);
    const res = await bff<LockResult>(`/api/bff/accounting/ledgers/${ledgerId}/lock`, { method: "POST", body: JSON.stringify({ until }) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setResult(res.data);
    router.refresh();
  };
  return (
    <form onSubmit={submit} className={`${ui.card} flex flex-col gap-2`} aria-label={t("lock.title")}>
      <h3 className="text-sm font-semibold">{t("lock.title")}</h3>
      <p className={ui.help}>{t("lock.help", { date: lockedUntil ? formatDate(lockedUntil) : t("lock.none") })}</p>
      <label className="flex flex-col gap-1 sm:w-1/3">
        <span className={ui.label}>{t("lock.until")}</span>
        <input type="date" required min={lockedUntil ?? undefined} className={ui.input} value={until} onChange={(e) => setUntil(e.target.value)} />
      </label>
      <div className={ui.formActions}>
        <button type="submit" className={ui.primary} disabled={busy || !until}>
          {t("lock.submit")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
      {result ? (
        <p role="status" className={ui.success}>
          {t("lock.done", {
            date: formatDate(result.locked_until),
            drafts: result.drafts_in_locked_period,
            unclarified: result.unclarified_bank_movements,
          })}
        </p>
      ) : null}
    </form>
  );
}
