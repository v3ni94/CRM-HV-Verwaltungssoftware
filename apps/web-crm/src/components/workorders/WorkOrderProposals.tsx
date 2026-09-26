"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type WorkOrderProposal = {
  id: string;
  work_order_id: string;
  starts_at: string;
  note: string | null;
  status: "proposed" | "accepted" | "declined" | "superseded";
  proposed_by_contact_id: string | null;
  decided_by_contact_id: string | null;
  decided_at: string | null;
  created_at: string;
};

export type WorkOrderProposalsData = {
  work_order_id: string;
  ticket_id: string | null;
  property_id: string;
  provider_contact_id: string;
  description: string;
  status: string;
  scheduled_at: string | null;
  confirmed_proposal_id: string | null;
  open_count: number;
  proposals: WorkOrderProposal[];
};

const BADGE: Record<WorkOrderProposal["status"], string> = {
  proposed: ui.badgeGold,
  accepted: ui.badgeSuccess,
  declined: ui.badge,
  superseded: ui.badge,
};

/** Terminvorschläge des Dienstleisters am Arbeitsauftrag (A58, A74): read only view for the
 *  office with the status of every proposal and the confirmed appointment of the order. The
 *  provider proposes and the affected resident accepts in the portal; nothing is decided
 *  here. */
export function WorkOrderProposals({ initial }: { initial: WorkOrderProposalsData }) {
  const t = useTranslations("WorkOrders");
  const [data, setData] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    setBusy(true);
    setError(null);
    const res = await bff<WorkOrderProposalsData>(`/api/bff/work-orders/${data.work_order_id}/appointment-proposals`);
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setData(res.data);
  }

  return (
    <section className="flex flex-col gap-3" data-testid="work-order-proposals">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className={ui.h2}>{t("proposals.title")}</h2>
        <span className={ui.badge}>{t(`orderStatus.${data.status}`)}</span>
        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void reload()}>
          {t("proposals.reload")}
        </button>
      </div>
      <p className={ui.help}>{t("proposals.hint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <p className={data.scheduled_at ? ui.success : ui.notice} data-testid="work-order-confirmed">
        {data.scheduled_at
          ? t("proposals.confirmed", { when: formatDateTime(data.scheduled_at) })
          : data.open_count > 0
            ? t("proposals.open", { n: data.open_count })
            : t("proposals.noneConfirmed")}
      </p>
      {data.proposals.length === 0 ? <p className="text-sm text-muted">{t("proposals.empty")}</p> : null}
      {data.proposals.length > 0 ? (
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("proposals.startsAt")}</th>
              <th>{t("proposals.note")}</th>
              <th>{t("proposals.status")}</th>
              <th>{t("proposals.decidedAt")}</th>
            </tr>
          </thead>
          <tbody>
            {data.proposals.map((p) => (
              <tr key={p.id} data-testid={`proposal-${p.status}`}>
                <td>{formatDateTime(p.starts_at)}</td>
                <td>{p.note ?? ""}</td>
                <td>
                  <span className={BADGE[p.status]}>{t(`proposals.statuses.${p.status}`)}</span>
                </td>
                <td>{p.decided_at ? formatDateTime(p.decided_at) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {data.ticket_id ? (
        <Link href={`/tickets/${data.ticket_id}`} className="text-sm hover:underline">
          {t("proposals.toTicket")}
        </Link>
      ) : null}
    </section>
  );
}
