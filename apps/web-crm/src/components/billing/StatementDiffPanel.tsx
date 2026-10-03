"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Delta = { old: string; new: string; delta: string };
type Diff = {
  version: number;
  tenants: { contract_id: string; unit_number: string | null; status: string; costs: Delta; advances_paid: Delta; balance: Delta }[];
  positions: { label: string; old: string | null; new: string | null; delta: string }[];
};

/** GAJ-104 (7.6 A01): difference report to the replaced statement version, shown for review
 *  before approval. Read only, values come from the stored snapshots. */
export function StatementDiffPanel({ statementId }: { statementId: string }) {
  const t = useTranslations("OperationsMasks.diff");
  const [diff, setDiff] = useState<Diff | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function load() {
    setBusy(true);
    setError(null);
    const res = await bff<Diff>(`/api/bff/statements/${statementId}/diff`);
    setBusy(false);
    if (res.ok) setDiff(res.data);
    else setError(res.message);
  }
  return (
    <section className="flex flex-col gap-2" data-testid="statement-diff">
      <h3 className={ui.h3}>{t("title")}</h3>
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
      {diff ? (
        <>
          <p className={ui.help}>{t("hint", { version: diff.version })}</p>
          {diff.tenants.length === 0 && diff.positions.length === 0 ? <p className={ui.help}>{t("none")}</p> : null}
          {diff.tenants.length > 0 ? (
            <div className={ui.tableScroll}>
              <table className={ui.table}>
                <thead>
                  <tr>
                    <th scope="col">{t("unit")}</th>
                    <th scope="col">{t("status")}</th>
                    <th scope="col" className="num">{t("costs")}</th>
                    <th scope="col" className="num">{t("balance")}</th>
                  </tr>
                </thead>
                <tbody>
                  {diff.tenants.map((r) => (
                    <tr key={r.contract_id}>
                      <td>{r.unit_number ?? ""}</td>
                      <td>{t(`statuses.${r.status}`)}</td>
                      <td className="num">{formatEur(r.costs.old)} → {formatEur(r.costs.new)} ({formatEur(r.costs.delta)})</td>
                      <td className="num">{formatEur(r.balance.old)} → {formatEur(r.balance.new)} ({formatEur(r.balance.delta)})</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {diff.positions.length > 0 ? (
            <div className={ui.tableScroll}>
              <table className={ui.table}>
                <thead>
                  <tr>
                    <th scope="col">{t("position")}</th>
                    <th scope="col" className="num">{t("old")}</th>
                    <th scope="col" className="num">{t("new")}</th>
                    <th scope="col" className="num">{t("delta")}</th>
                  </tr>
                </thead>
                <tbody>
                  {diff.positions.map((p) => (
                    <tr key={p.label}>
                      <td>{p.label}</td>
                      <td className="num">{p.old === null ? "" : formatEur(p.old)}</td>
                      <td className="num">{p.new === null ? "" : formatEur(p.new)}</td>
                      <td className="num">{formatEur(p.delta)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
