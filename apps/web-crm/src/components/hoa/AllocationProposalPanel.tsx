"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Ref = { contract_id: string; contract_number: string | null } | null;
type Proposal = {
  resolution_day: string;
  items: { unit_id: string; unit_number: string | null; result: string; used: Ref; proposed: Ref; differs: boolean }[];
  note: string;
};

/** GAJ-201 (7.8 W07): proposal for the debtor of the statement result at an owner change.
 *  A proposal only: no posting, no decision; the rule itself is open (AA11-03). */
export function AllocationProposalPanel({ statementId }: { statementId: string }) {
  const t = useTranslations("OperationsMasks.proposal");
  const [data, setData] = useState<Proposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function load() {
    setBusy(true);
    setError(null);
    const res = await bff<Proposal>(`/api/bff/hoa/statements/${statementId}/allocation-proposal`);
    setBusy(false);
    if (res.ok) setData(res.data);
    else setError(res.message);
  }
  const label = (r: Ref) => (r ? (r.contract_number ?? r.contract_id.slice(0, 8)) : t("noOwner"));
  return (
    <section className={`${ui.card} flex flex-col gap-2`} data-testid="allocation-proposal">
      <h3 className={ui.h3}>{t("title")}</h3>
      <p className={ui.notice}>{t("notice")}</p>
      <div>
        <button type="button" className={ui.button} onClick={() => void load()} disabled={busy}>
          {t("load")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {data ? (
        data.items.length === 0 ? (
          <p className={ui.help}>{t("empty")}</p>
        ) : (
          <>
            <p className={ui.help}>{t("day", { date: formatDate(data.resolution_day) })}</p>
            <div className={ui.tableScroll}>
              <table className={ui.table}>
                <thead>
                  <tr>
                    <th scope="col">{t("unit")}</th>
                    <th scope="col" className="num">{t("result")}</th>
                    <th scope="col">{t("used")}</th>
                    <th scope="col">{t("proposed")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((i) => (
                    <tr key={i.unit_id}>
                      <td>{i.unit_number ?? ""}</td>
                      <td className="num">{formatEur(i.result)}</td>
                      <td>{label(i.used)}</td>
                      <td>
                        {label(i.proposed)} {i.differs ? <span className={ui.badgeWarning}>{t("differs")}</span> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )
      ) : null}
    </section>
  );
}
