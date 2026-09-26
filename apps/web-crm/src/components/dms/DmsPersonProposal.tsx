"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import {
  PROPOSAL_ROW_STATUSES,
  dmsBase,
  type PersonKind,
  type PersonProposal,
  type ProposalRowStatus,
} from "@/lib/objektakte-dms";
import { ui } from "@/lib/ui";

const BADGE: Record<ProposalRowStatus, string> = {
  unchanged: ui.badgeSuccess,
  new: ui.badgeGold,
  conflict: ui.badgeWarning,
  unit_unknown: ui.badgeDanger,
  no_unit: ui.badgeDanger,
  crm_only: ui.badge,
};

/** M29 Stufe 4: owner and tenant list of objektakte as an import proposal (M8 pattern). "Abruf
 *  und Testlauf" fetches the list and reconciles it with the current contracts; the release only
 *  confirms the reconciliation as working basis. Nothing is written into the master data. */
export function DmsPersonProposal({ number }: { number: string }) {
  const t = useTranslations("Dms");
  const [kind, setKind] = useState<PersonKind>("owners");
  const [proposal, setProposal] = useState<PersonProposal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (path: string, body?: unknown) => {
    setBusy(true);
    setError(null);
    const res = await bff<PersonProposal>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setProposal(res.data);
  };

  const start = () => run(`${dmsBase(number)}/person-proposals`, { kind });
  const action = (verb: "test-run" | "approve" | "reject") =>
    proposal ? run(`/api/bff/integrations/objektakte/person-proposals/${proposal.id}/${verb}`) : undefined;

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("proposal.title")}>
      <h2 className={ui.h2}>{t("proposal.title")}</h2>
      <p className="text-xs text-muted">{t("proposal.hint")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("proposal.kind")}</span>
          <select className={ui.input} value={kind} onChange={(e) => setKind(e.target.value as PersonKind)}>
            <option value="owners">{t("proposal.owners")}</option>
            <option value="tenants">{t("proposal.tenants")}</option>
          </select>
        </label>
        <button type="button" className={ui.primary} onClick={() => void start()} disabled={busy} data-testid="dms-proposal-start">
          {t("proposal.start")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {proposal ? (
        <div className="flex flex-col gap-3" data-testid="dms-proposal">
          <p className="text-sm">
            {t("proposal.state", {
              status: t(`proposal.status.${proposal.status}`),
              fetched: formatDateTime(proposal.fetched_at),
              date: formatDate(proposal.summary.reference_date),
            })}
          </p>
          <ul className="flex flex-wrap gap-2">
            {PROPOSAL_ROW_STATUSES.map((s) => (
              <li key={s} className={BADGE[s]}>
                {t(`proposal.row.${s}`)}: {proposal.summary.counts[s] ?? 0}
              </li>
            ))}
          </ul>
          <div className="overflow-x-auto">
            <table className={ui.table} data-testid="dms-proposal-rows">
              <thead>
                <tr>
                  <th>{t("proposal.colName")}</th>
                  <th>{t("proposal.colUnits")}</th>
                  <th>{t("proposal.colResult")}</th>
                  <th>{t("proposal.colCrm")}</th>
                </tr>
              </thead>
              <tbody>
                {proposal.rows.map((r, index) => (
                  <tr key={`${r.source_id ?? "crm"}-${index}`}>
                    <td>{r.display_name}</td>
                    <td>{r.unit_labels.join(", ")}</td>
                    <td>
                      <span className={BADGE[r.status]}>{t(`proposal.row.${r.status}`)}</span>
                    </td>
                    <td>{r.units.flatMap((u) => u.crm_names ?? []).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {proposal.status === "tested" ? (
            <div className={ui.formActions}>
              <button type="button" className={ui.button} onClick={() => void action("test-run")} disabled={busy}>
                {t("proposal.rerun")}
              </button>
              <button type="button" className={ui.primary} onClick={() => void action("approve")} disabled={busy} data-testid="dms-proposal-approve">
                {t("proposal.approve")}
              </button>
              <button type="button" className={ui.secondary} onClick={() => void action("reject")} disabled={busy}>
                {t("proposal.reject")}
              </button>
            </div>
          ) : (
            <p className={ui.notice}>{t("proposal.decided")}</p>
          )}
        </div>
      ) : null}
    </section>
  );
}
