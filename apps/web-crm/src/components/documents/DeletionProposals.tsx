"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

import { DeletionChecklist } from "./DeletionChecklist";

export type DeletionProposalItem = {
  id: string;
  document_id: string;
  title: string;
  sha256: string;
  category_code: string | null;
  document_class: string;
  retention_until: string;
  status: string;
  skip_reason: string | null;
  deleted_at: string | null;
  deleted_by: string | null;
  mirror_deletions: number;
};

export type DeletionProposal = {
  id: string;
  status: string;
  reference_date: string;
  created_at: string;
  created_by: string | null;
  approved_by: string | null;
  approved_at: string | null;
  rejected_by: string | null;
  rejected_at: string | null;
  executed_by: string | null;
  executed_at: string | null;
  note: string | null;
  items: DeletionProposalItem[];
};

/** Löschvorschläge (M6-04): Lauf starten, freigeben (nicht durch den Ersteller), ausführen
 *  (nicht durch den Freigeber), ablehnen; jede Zeile ist der Protokolleintrag mit Hash,
 *  Klasse, Kategorie, Zeitpunkt und Freigeber. */
export function DeletionProposals({
  proposals: initial,
  userId,
  canApprove,
  canDelete,
}: {
  proposals: DeletionProposal[];
  userId: string | null;
  canApprove: boolean;
  canDelete: boolean;
}) {
  const t = useTranslations("DeletionProposals");
  const [proposals, setProposals] = useState(initial);
  const [open, setOpen] = useState<string | null>(initial[0]?.id ?? null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const replace = (next: DeletionProposal) => setProposals((list) => list.map((p) => (p.id === next.id ? next : p)));
  const statusBadge = (status: string) => {
    const label = t.has(`status.${status}`) ? t(`status.${status}`) : status;
    if (status === "approved") return <span className={ui.badgeInfo}>{label}</span>;
    if (status === "executed") return <span className={ui.badgeSuccess}>{label}</span>;
    if (status === "rejected") return <span className={ui.badge}>{label}</span>;
    return <span className={ui.badgeWarning}>{label}</span>;
  };
  const itemBadge = (status: string) => {
    const label = t.has(`itemStatus.${status}`) ? t(`itemStatus.${status}`) : status;
    if (status === "deleted") return <span className={ui.badgeSuccess}>{label}</span>;
    if (status === "skipped") return <span className={ui.badgeWarning}>{label}</span>;
    return <span className={ui.badge}>{label}</span>;
  };

  const run = async (path: string, init: RequestInit, done: (p: DeletionProposal) => void, ok: string) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<DeletionProposal>(path, init);
    setBusy(false);
    if (res.ok) {
      done(res.data);
      setMessage(ok);
    } else setError(res.message);
  };

  const create = () =>
    run(
      "/api/bff/deletion-proposals",
      { method: "POST" },
      (p) => {
        setProposals((list) => [p, ...list]);
        setOpen(p.id);
      },
      t("created"),
    );
  const approve = (id: string) => run(`/api/bff/deletion-proposals/${id}/approve`, { method: "POST" }, replace, t("approved"));
  const reject = (id: string) =>
    run(
      `/api/bff/deletion-proposals/${id}/reject`,
      { method: "POST", body: JSON.stringify({ note: note.trim() || null }) },
      replace,
      t("rejected"),
    );
  const execute = async (id: string) => {
    if (!window.confirm(t("executeConfirm"))) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<{ proposal: DeletionProposal; deleted: number; skipped: number }>(
      `/api/bff/deletion-proposals/${id}/execute`,
      { method: "POST" },
    );
    setBusy(false);
    if (res.ok) {
      replace(res.data.proposal);
      setMessage(t("executed", { deleted: res.data.deleted, skipped: res.data.skipped }));
    } else setError(res.message);
  };

  return (
    <div className="flex flex-col gap-4">
      <p className={ui.notice}>{t("rules")}</p>
      {canDelete ? (
        <div>
          <button type="button" className={ui.secondary} disabled={busy} onClick={() => void create()}>
            {t("createNow")}
          </button>
          <p className={ui.help}>{t("createHint")}</p>
        </div>
      ) : null}
      {message ? <p className={ui.success}>{message}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {proposals.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        proposals.map((p) => {
          const isOpen = open === p.id;
          const mayApprove = canApprove && p.status === "open" && userId !== null && p.created_by !== userId;
          const mayExecute = canDelete && p.status === "approved" && userId !== null && p.approved_by !== userId;
          const mayReject = canApprove && (p.status === "open" || p.status === "approved");
          return (
            <section key={p.id} className={`${ui.card} flex flex-col gap-3`} data-testid="deletion-proposal">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-sm font-semibold">
                    {t("proposalTitle", { date: formatDate(p.reference_date) })} {statusBadge(p.status)}
                  </h2>
                  <p className={ui.small}>
                    {t("counts", { total: p.items.length, deleted: p.items.filter((i) => i.status === "deleted").length })}
                    {" "}
                    {p.created_by ? t("byUser") : t("byJob")}
                    {p.approved_at ? `, ${t("approvedAt", { at: formatDateTime(p.approved_at) })}` : ""}
                    {p.executed_at ? `, ${t("executedAt", { at: formatDateTime(p.executed_at) })}` : ""}
                    {p.rejected_at ? `, ${t("rejectedAt", { at: formatDateTime(p.rejected_at) })}` : ""}
                    {p.note ? ` (${p.note})` : ""}
                  </p>
                </div>
                <div className="flex flex-wrap gap-1">
                  <button type="button" className={ui.buttonSm} onClick={() => setOpen(isOpen ? null : p.id)}>
                    {isOpen ? t("hide") : t("show")}
                  </button>
                  {p.status === "open" && canApprove ? (
                    <button
                      type="button"
                      className={ui.buttonSm}
                      disabled={busy || !mayApprove}
                      title={mayApprove ? undefined : t("fourEyesApprove")}
                      onClick={() => void approve(p.id)}
                    >
                      {t("approve")}
                    </button>
                  ) : null}
                  {p.status === "approved" && canDelete ? (
                    <button
                      type="button"
                      className={ui.buttonSm}
                      disabled={busy || !mayExecute}
                      title={mayExecute ? undefined : t("fourEyesExecute")}
                      onClick={() => void execute(p.id)}
                    >
                      {t("execute")}
                    </button>
                  ) : null}
                  {mayReject ? (
                    <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void reject(p.id)}>
                      {t("reject")}
                    </button>
                  ) : null}
                </div>
              </div>
              {mayReject && isOpen ? (
                <input
                  aria-label={t("notePlaceholder")}
                  className={ui.input}
                  placeholder={t("notePlaceholder")}
                  value={note}
                  maxLength={500}
                  onChange={(e) => setNote(e.target.value)}
                />
              ) : null}
              {isOpen ? (
                <div className="overflow-x-auto">
                  <table className={ui.table}>
                    <thead>
                      <tr>
                        <th>{t("colTitle")}</th>
                        <th>{t("colClass")}</th>
                        <th>{t("colUntil")}</th>
                        <th>{t("colStatus")}</th>
                        <th>{t("colHash")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {p.items.map((i) => (
                        <tr key={i.id}>
                          <td>
                            {i.status === "deleted" ? i.title : <Link href={`/dokumente/${i.document_id}`}>{i.title}</Link>}
                            {i.category_code ? <div className={ui.small}>{i.category_code}</div> : null}
                          </td>
                          <td>{i.document_class}</td>
                          <td>{formatDate(i.retention_until)}</td>
                          <td>
                            {itemBadge(i.status)}
                            {i.skip_reason ? <div className={ui.small}>{i.skip_reason}</div> : null}
                            {i.deleted_at ? (
                              <div className={ui.small}>
                                {formatDateTime(i.deleted_at)}
                                {i.mirror_deletions > 0 ? `, ${t("mirrorSteps", { count: i.mirror_deletions })}` : ""}
                              </div>
                            ) : null}
                            {i.status === "deleted" ? (
                              <DeletionChecklist documentId={i.document_id} canDelete={canDelete} />
                            ) : null}
                          </td>
                          <td>
                            <span className={ui.mono} title={i.sha256}>
                              {i.sha256.slice(0, 12)}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </section>
          );
        })
      )}
    </div>
  );
}
