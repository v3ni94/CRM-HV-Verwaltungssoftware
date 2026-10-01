"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type ReserveRow = {
  id: string;
  name: string;
  purpose: string | null;
  active?: boolean;
  opening_balance?: string;
  opening_year?: number | null;
};

type YearRow = {
  year: number;
  opening: string;
  contributions: string;
  contribution_basis: "paid" | "planned";
  withdrawals: string;
  taxes: string;
  fees: string;
  interest: string;
  closing: string;
  source: "statement" | "plan" | "none";
};

type Movement = { id: string; reserve_id: string; kind: string; amount: string; purpose: string; receipt_linked: boolean };

/** One earmarked reserve (M24-01): master data change and development per year (opening,
 *  contribution, withdrawal, taxes, fees, interest, closing). Nothing here posts. */
export function ReservePosition({ reserve, year }: { reserve: ReserveRow; year: number }) {
  const t = useTranslations("HoaReserves");
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(reserve.name);
  const [opening, setOpening] = useState(reserve.opening_balance ?? "0.00");
  const [openingYear, setOpeningYear] = useState(reserve.opening_year ? String(reserve.opening_year) : "");
  const [rows, setRows] = useState<YearRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const res = await bff(`/api/bff/hoa/reserves/${reserve.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: name.trim(),
        opening_balance: opening.replace(",", "."),
        opening_year: openingYear ? Number(openingYear) : null,
      }),
    });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setEditing(false);
    setRows(null);
    router.refresh();
  }

  async function load() {
    setError(null);
    const res = await bff<{ years: YearRow[] }>(`/api/bff/hoa/reserves/${reserve.id}/development?year=${year}`);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setRows(res.data.years);
  }

  return (
    <li className="flex flex-col gap-1" data-testid="reserve-position">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{reserve.name}</span>
        {reserve.purpose ? <span className="text-muted">· {reserve.purpose}</span> : null}
        {reserve.opening_year ? (
          <span className="text-muted">
            · {t("openingBalance")} {formatEur(reserve.opening_balance ?? "0")} ({reserve.opening_year})
          </span>
        ) : null}
        {reserve.active === false ? <span className="text-muted">· {t("inactive")}</span> : null}
        <button type="button" className={ui.buttonSm} onClick={() => setEditing((v) => !v)}>
          {editing ? t("cancel") : t("edit")}
        </button>
        <button type="button" className={ui.buttonSm} onClick={load}>
          {t("loadDevelopment")}
        </button>
      </div>
      {editing ? (
        <form onSubmit={save} className="flex flex-wrap items-end gap-2" aria-label={t("edit")}>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("name")}</span>
            <input className={ui.input} value={name} onChange={(e) => setName(e.target.value)} minLength={2} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("openingBalance")}</span>
            <input className={ui.input} inputMode="decimal" value={opening} onChange={(e) => setOpening(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("openingYear")}</span>
            <input className={ui.input} inputMode="numeric" value={openingYear} onChange={(e) => setOpeningYear(e.target.value)} />
          </label>
          <button type="submit" className={ui.button} disabled={name.trim().length < 2}>
            {t("save")}
          </button>
        </form>
      ) : null}
      {rows ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" aria-label={t("yearTitle")}>
            <thead>
              <tr className="text-left">
                <th>{t("year")}</th>
                <th>{t("opening")}</th>
                <th>{t("contribution")}</th>
                <th>{t("withdrawals")}</th>
                <th>{t("taxes")}</th>
                <th>{t("fees")}</th>
                <th>{t("interest")}</th>
                <th>{t("closing")}</th>
                <th>{t("basis")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.year}>
                  <td>{r.year}</td>
                  <td>{formatEur(r.opening)}</td>
                  <td>{formatEur(r.contributions)}</td>
                  <td>{formatEur(r.withdrawals)}</td>
                  <td>{formatEur(r.taxes)}</td>
                  <td>{formatEur(r.fees)}</td>
                  <td>{formatEur(r.interest)}</td>
                  <td className="font-medium">{formatEur(r.closing)}</td>
                  <td>
                    {r.source === "statement" ? t("sourceStatement") : r.source === "plan" ? t("sourcePlan") : t("sourceNone")}
                    {r.source !== "none" ? ` (${r.contribution_basis === "paid" ? t("basisPaid") : t("basisPlanned")})` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className={ui.help}>{t("developmentHint")}</p>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </li>
  );
}

/** Recorded uses of funds of one statement with receipt state; removal only in the draft. */
export function ReserveMovementList({ statementId, reserves, editable }: { statementId: string; reserves: ReserveRow[]; editable: boolean }) {
  const t = useTranslations("HoaReserves");
  const [items, setItems] = useState<Movement[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const names = new Map(reserves.map((r) => [r.id, r.name]));

  async function load() {
    const res = await bff<Movement[]>(`/api/bff/hoa/statements/${statementId}/reserve-movements`);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setItems(res.data);
  }

  async function remove(id: string) {
    setError(null);
    const res = await bff(`/api/bff/hoa/statements/${statementId}/reserve-movements/${id}`, { method: "DELETE" });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setItems((list) => (list ?? []).filter((m) => m.id !== id));
  }

  return (
    <section className="flex flex-col gap-2" data-testid="reserve-movements">
      <div className="flex items-center gap-2">
        <h3 className="font-medium">{t("movementsTitle")}</h3>
        <button type="button" className={ui.buttonSm} onClick={load}>
          {t("showMovements")}
        </button>
      </div>
      {items && items.length === 0 ? <p className="text-sm text-muted">{t("noMovements")}</p> : null}
      {items && items.length ? (
        <ul className="flex flex-col gap-1 text-sm">
          {items.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center gap-2">
              <span>{names.get(m.reserve_id) ?? m.reserve_id}</span>
              <span>· {t(`kinds.${m.kind}`)}</span>
              <span>· {formatEur(m.amount)}</span>
              <span className="text-muted">· {m.purpose}</span>
              <span className={m.receipt_linked ? "text-muted" : "text-danger"}>· {m.receipt_linked ? t("receipt") : t("receiptMissing")}</span>
              {editable ? (
                <button type="button" className={ui.buttonSm} onClick={() => remove(m.id)}>
                  {t("remove")}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
