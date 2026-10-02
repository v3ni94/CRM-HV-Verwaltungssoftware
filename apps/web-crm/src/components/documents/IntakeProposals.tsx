"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type IntakeFollowup = { kind: string; label: string; status: string };
export type IntakeProposal = {
  id: string;
  document_id: string;
  document_title: string | null;
  source: string;
  confidence: number;
  proposed: Record<string, unknown>;
  decision: string;
  decided_at: string | null;
  final: { auto_filed?: boolean; reason?: string; followups?: IntakeFollowup[] } | null;
  created_at: string;
};
type Page = { data: IntakeProposal[]; meta: Record<string, number> };

const API = "/api/bff/documents/intake-proposals";
const FILTERS = ["pending", "accepted", "modified", "rejected", "all"] as const;

/** Dokumenteingang (Abschnitt 8, 11.4): Vorschläge prüfen, annehmen oder ablehnen, Folgeaktionen
 *  bestätigen, automatische Ablage zurücknehmen. Die KI schlägt nur vor, die Entscheidung trifft
 *  eine Person; Folgeaktionen verknüpfen höchstens, gebucht wird hier nichts. */
export function IntakeProposals({ canUpdate }: { canUpdate: boolean }) {
  const t = useTranslations("IntakeProposals");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("pending");
  const [rows, setRows] = useState<IntakeProposal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    const res = await bff<Page>(`${API}?decision=${filter}&page_size=100`);
    if (res.ok) setRows(res.data.data);
    else setError(res.message);
  }, [filter]);
  useEffect(() => {
    void load();
  }, [load]);

  const act = async (path: string, body: unknown) => {
    setBusy(true);
    setError(null);
    const res = await bff<IntakeProposal>(`${API}/${path}`, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setRejecting(null);
    setReason("");
    await load();
  };

  // GAB-11 "Beleg erfassen": the receipt extraction starts as a proposal (POST receipts/drafts,
  // the AI approvals apply there), then the hint is marked as handed over.
  const captureReceipt = async (proposalId: string, documentId: string) => {
    setBusy(true);
    setError(null);
    const res = await bff<unknown>("/api/bff/receipts/drafts", { method: "POST", body: JSON.stringify({ document_id: documentId }) });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    await act(`${proposalId}/followups/invoice/confirm`, {});
  };

  return (
    <section className="flex flex-col gap-3" aria-label={t("title")}>
      <label className="flex max-w-xs flex-col gap-1">
        <span className={ui.label}>{t("filter")}</span>
        <select className={ui.input} value={filter} onChange={(e) => setFilter(e.target.value as (typeof FILTERS)[number])}>
          {FILTERS.map((f) => (
            <option key={f} value={f}>
              {t(`decision.${f}`)}
            </option>
          ))}
        </select>
      </label>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {rows === null ? null : rows.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <ul className="flex flex-col gap-2">
          {rows.map((p) => {
            const followups = (p.final?.followups ?? []).filter((f) => f.status === "proposed");
            return (
              <li key={p.id} className={ui.card} data-testid="intake-proposal">
                <div className="flex flex-wrap items-center gap-2">
                  <Link href={`/dokumente/${p.document_id}`} className="font-medium underline">
                    {p.document_title ?? t("untitled")}
                  </Link>
                  <span className={ui.badge}>{t(`decision.${p.decision}`)}</span>
                  <span className={ui.badgeInfo}>{t("source", { source: p.source || "-" })}</span>
                  <span className={ui.help}>{t("confidence", { value: Math.round(p.confidence * 100) })}</span>
                  <span className={ui.help}>{formatDateTime(p.created_at)}</span>
                </div>
                {p.final?.reason ? <p className={ui.help}>{t("reason", { reason: p.final.reason })}</p> : null}
                {canUpdate ? (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {p.decision === "pending" ? (
                      <>
                        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void act(`${p.id}/accept`, {})}>
                          {t("accept")}
                        </button>
                        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => setRejecting(p.id)}>
                          {t("reject")}
                        </button>
                      </>
                    ) : null}
                    {p.final?.auto_filed ? (
                      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void act(`${p.id}/revert-auto`, {})}>
                        {t("revert")}
                      </button>
                    ) : null}
                    {followups.map((f) => (
                      <button key={f.kind} type="button" className={ui.buttonSm} disabled={busy} onClick={() => void (f.kind === "invoice" ? captureReceipt(p.id, p.document_id) : act(`${p.id}/followups/${f.kind}/confirm`, {}))}>
                        {f.kind === "invoice" ? t("captureReceipt") : t("confirmFollowup", { label: f.label })}
                      </button>
                    ))}
                  </div>
                ) : null}
                {rejecting === p.id ? (
                  <form
                    className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-end"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void act(`${p.id}/reject`, reason ? { reason } : {});
                    }}
                  >
                    <label className="flex flex-1 flex-col gap-1">
                      <span className={ui.label}>{t("rejectReason")}</span>
                      <input className={ui.input} value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
                    </label>
                    <button type="submit" className={ui.buttonSm} disabled={busy}>
                      {t("rejectConfirm")}
                    </button>
                  </form>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
