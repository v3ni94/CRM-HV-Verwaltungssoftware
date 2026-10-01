"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Row = {
  reserve_id: string;
  name: string;
  planned: string;
  paid_bound: string;
  open_bound: string;
  paid_proposal?: string;
  paid_with_proposal?: string;
};
type Payload = { mode: string; paid_unassigned: string; reserves: Row[] };

/** AE08 (P07-02): Soll and Ist per earmarked reserve; with the plan ratio variant also the
 *  proposed split of unbound payments. Information only, nothing is posted. */
export function ReservePayments({ ledgerId, year }: { ledgerId: string; year: number }) {
  const t = useTranslations("HoaReservePayments");
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    const res = await bff<Payload>(`/api/bff/hoa/ledgers/${ledgerId}/reserve-payments?year=${year}`);
    if (!res.ok) {
      setError(t("error"));
      return;
    }
    setData(res.data);
  }

  const proposal = data?.mode === "plan_ratio_proposal";
  return (
    <section className="flex flex-col gap-2" data-testid="reserve-payments">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="text-sm">{t("hint")}</p>
      <div>
        <button type="button" className={ui.buttonSm} onClick={() => void load()}>
          {t("load")}
        </button>
      </div>
      {error ? <p role="alert">{error}</p> : null}
      {data ? (
        <>
          <div className={ui.tableScroll}>
          <table className={ui.table}>
            <caption className="text-left">{t(`mode.${data.mode}`)}</caption>
            <thead>
              <tr>
                <th>{t("reserve")}</th>
                <th>{t("planned")}</th>
                <th>{t("paidBound")}</th>
                <th>{t("openBound")}</th>
                {proposal ? <th>{t("paidProposal")}</th> : null}
              </tr>
            </thead>
            <tbody>
              {data.reserves.map((r) => (
                <tr key={r.reserve_id}>
                  <td>{r.name}</td>
                  <td>{formatEur(r.planned)}</td>
                  <td>{formatEur(r.paid_bound)}</td>
                  <td>{formatEur(r.open_bound)}</td>
                  {proposal ? <td>{formatEur(r.paid_proposal ?? "0.00")}</td> : null}
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <p className="text-sm">
            {t("unassigned")}: {formatEur(data.paid_unassigned)}
          </p>
        </>
      ) : null}
    </section>
  );
}
