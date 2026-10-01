"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Item = { account_id: string; number: string; name: string; category: string; balance: string };
type Preview = {
  fiscal_year: number;
  start: string;
  end: string;
  target_date: string;
  carried: Item[];
  not_carried: Item[];
  already_drafted: boolean;
  note: string;
};

/** Q02 (Jahresübernahme): Schlussbestände eines beendeten Geschäftsjahres anzeigen und als
 * Anfangsbestand übernehmen. Es entstehen nur Entwürfe (Schlussbestand und Anfangsbestand),
 * die wie jede andere Buchung geprüft und von einer zweiten Person freigegeben werden. */
export function YearCarryoverPanel({ ledgerId, defaultYear }: { ledgerId: string; defaultYear: number }) {
  const t = useTranslations("YearCarryover");
  const router = useRouter();
  const [year, setYear] = useState(String(defaultYear));
  const [data, setData] = useState<Preview | null>(null);
  const [created, setCreated] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const yearOk = /^\d{4}$/.test(year) && Number(year) >= 2000 && Number(year) <= 2100;
  const url = `/api/bff/accounting/ledgers/${ledgerId}/year-carryover?fiscal_year=${year}`;

  const load = async () => {
    setBusy(true);
    setError(null);
    setCreated(null);
    const res = await bff<Preview>(url);
    setBusy(false);
    if (!res.ok) {
      setData(null);
      return setError(res.message);
    }
    setData(res.data);
  };
  const take = async () => {
    if (!window.confirm(t("confirm", { year, next: String(Number(year) + 1) }))) return;
    setBusy(true);
    setError(null);
    const res = await bff<unknown[]>(url, { method: "POST" });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setCreated(res.data?.length ?? 0);
    setData((d) => (d ? { ...d, already_drafted: true } : d));
    router.refresh();
  };
  const table = (rows: Item[], testId: string) => (
    <div className="overflow-x-auto">
      <table className="mhvp-table" data-testid={testId}>
        <thead>
          <tr>
            <th>{t("account")}</th>
            <th>{t("category")}</th>
            <th className="num">{t("balance")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.account_id}>
              <td>{r.number} {r.name}</td>
              <td>{r.category}</td>
              <td className="num">{formatEur(r.balance)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <section className="flex flex-col gap-2" data-testid="year-carryover">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.help}>{t("hint")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("year")}</span>
          <input className={`${ui.input} w-28`} inputMode="numeric" value={year} onChange={(e) => { setYear(e.target.value); setData(null); setCreated(null); }} />
        </label>
        <button type="button" className={ui.button} onClick={() => void load()} disabled={busy || !yearOk}>{t("show")}</button>
        {data && !data.already_drafted && data.carried.length > 0 ? (
          <button type="button" className={ui.primary} onClick={() => void take()} disabled={busy}>{t("take")}</button>
        ) : null}
      </div>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {created !== null ? <p role="status" className={ui.success}>{t("created", { count: created })}</p> : null}
      {data ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm">{t("period", { start: formatDate(data.start), end: formatDate(data.end), target: formatDate(data.target_date) })}</p>
          {data.already_drafted ? <p className={ui.notice}>{t("alreadyDrafted")}</p> : null}
          <h3 className="text-sm font-semibold">{t("carried")}</h3>
          {data.carried.length === 0 ? <p className={ui.help}>{t("noneCarried")}</p> : table(data.carried, "carried")}
          {data.not_carried.length > 0 ? (
            <>
              <h3 className="text-sm font-semibold">{t("notCarried")}</h3>
              {table(data.not_carried, "not-carried")}
            </>
          ) : null}
          <p className={ui.help}>{data.note}</p>
        </div>
      ) : null}
    </section>
  );
}
