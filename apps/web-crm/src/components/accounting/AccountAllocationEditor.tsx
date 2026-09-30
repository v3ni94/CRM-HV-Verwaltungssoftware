"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { toDecimal } from "./JournalEntryForm";

export type AllocationKeyOption = { id: string; code: string; name: string };
type Row = { allocation_key_id: string; share_percent: string };
type AllocationOut = { items: { allocation_key_id: string; share_percent: string }[]; total_percent: string };

/** Sum of percent strings with four decimals, as integers (no float drift). */
export function sumBasisPoints(values: string[]): number {
  return values.reduce((acc, value) => {
    const [whole = "0", frac = ""] = toDecimal(value).split(".");
    return acc + (Number.parseInt(whole, 10) || 0) * 10000 + (Number.parseInt((frac + "0000").slice(0, 4), 10) || 0);
  }, 0);
}

const trimPercent = (value: string) => value.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");

/** Verteilung eines Kostenkontos auf Umlageschlüssel (M10-01), Summe genau 100 %. */
export function AccountAllocationEditor({
  ledgerId,
  accountId,
  keys,
  canUpdate,
}: {
  ledgerId: string;
  accountId: string;
  keys: AllocationKeyOption[];
  canUpdate: boolean;
}) {
  const t = useTranslations("Bookkeeping");
  const url = `/api/bff/accounting/ledgers/${ledgerId}/accounts/${accountId}/allocations`;
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    void bff<AllocationOut>(url).then((res) => {
      if (!alive) return;
      if (res.ok) setRows(res.data.items.map((i) => ({ allocation_key_id: i.allocation_key_id, share_percent: trimPercent(String(i.share_percent)) })));
      else setError(res.message);
    });
    return () => {
      alive = false;
    };
  }, [url]);

  const total = sumBasisPoints(rows.map((r) => r.share_percent));
  const valid = rows.length === 0 || total === 1_000_000;
  const setRow = (i: number, patch: Partial<Row>) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setInfo(null);
    if (!valid) {
      setError(t("allocation.not100"));
      return;
    }
    setBusy(true);
    const res = await bff<AllocationOut>(url, {
      method: "PUT",
      body: JSON.stringify({ items: rows.map((r) => ({ allocation_key_id: r.allocation_key_id, share_percent: toDecimal(r.share_percent) })) }),
    });
    setBusy(false);
    if (res.ok) setInfo(t("allocation.saved"));
    else setError(res.message);
  };

  return (
    <form onSubmit={save} className={`${ui.card} flex flex-col gap-3`} aria-label={t("allocation.title")}>
      <h3 className="text-sm font-semibold">{t("allocation.title")}</h3>
      <p className={ui.help}>{t("allocation.help")}</p>
      {keys.length === 0 ? <p className={ui.notice}>{t("allocation.noKeys")}</p> : null}
      {rows.map((row, i) => (
        <div key={i} className="grid gap-2 sm:grid-cols-[2fr_1fr_auto]">
          <select aria-label={t("allocation.key")} required disabled={!canUpdate} className={ui.input} value={row.allocation_key_id} onChange={(e) => setRow(i, { allocation_key_id: e.target.value })}>
            <option value="">{t("allocation.chooseKey")}</option>
            {keys.map((k) => (
              <option key={k.id} value={k.id}>
                {k.code} {k.name}
              </option>
            ))}
          </select>
          <input aria-label={t("allocation.share")} required inputMode="decimal" disabled={!canUpdate} className={ui.input} value={row.share_percent} onChange={(e) => setRow(i, { share_percent: e.target.value })} />
          {canUpdate ? (
            <button type="button" className={ui.buttonSm} onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}>
              {t("allocation.remove")}
            </button>
          ) : null}
        </div>
      ))}
      <p className={valid ? "text-sm tabular-nums" : `text-sm tabular-nums ${ui.error}`} data-testid="allocation-total">
        {t("allocation.total", { total: (total / 10000).toLocaleString("de-DE", { maximumFractionDigits: 4 }) })}
      </p>
      {canUpdate ? (
        <div className={ui.formActions}>
          <button type="button" className={ui.secondary} disabled={keys.length === 0} onClick={() => setRows((rs) => [...rs, { allocation_key_id: "", share_percent: "" }])}>
            {t("allocation.add")}
          </button>
          <button type="submit" className={ui.primary} disabled={busy || !valid}>
            {t("allocation.save")}
          </button>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
      {info ? (
        <p role="status" className={ui.success}>
          {info}
        </p>
      ) : null}
    </form>
  );
}
