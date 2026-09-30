"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type ClarificationRow = {
  id: string;
  bank_transaction_id: string;
  legal_entity_id: string;
  status: "open" | "in_clarification" | "receipt_requested" | "no_document_required" | "resolved" | string;
  reasons: string[];
  rule_id: string | null;
  reason: string | null;
  document_id: string | null;
  ticket_id: string | null;
  assignee_user_id: string | null;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
  age_days?: number | null;
  booking_date: string | null;
  amount: string | null;
  counterpart_name: string | null;
  purpose: string | null;
  transaction_status: string | null;
};

export type BankClarificationsProps = { canUpdate: boolean };

/** Liste "Buchungen ohne Beleg" (B05, Regel M12-05): unbelegte Bankbewegungen mit Klärungsstatus und
 *  verantwortlicher Aufgabe. Eine Person setzt In Klärung, Kein Beleg erforderlich (mit Begründung) oder
 *  Erledigt (mit Beleg-ID) oder fordert den Beleg an; das Alter zählt ab dem Buchungstag. Die Liste bucht nichts; sie ist vor jeder Festschreibung zu leeren. */
export function BankClarifications({ canUpdate }: BankClarificationsProps) {
  const t = useTranslations("Bank.clarifications");
  const [rows, setRows] = useState<ClarificationRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [deciding, setDeciding] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [documentId, setDocumentId] = useState("");

  const load = useCallback(async () => {
    const res = await bff<ClarificationRow[]>("/api/bff/banking/clarifications");
    if (res.ok) setRows(res.data);
    else {
      setRows([]);
      setError(res.message);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const decide = async (row: ClarificationRow, status: string) => {
    setBusy(row.id);
    setError(null);
    const body: Record<string, unknown> = { status };
    if (status === "no_document_required") body.reason = reason.trim();
    if (status === "resolved") body.document_id = documentId.trim();
    const res = await bff<ClarificationRow>(`/api/bff/banking/clarifications/${row.id}`, { method: "POST", body: JSON.stringify(body) });
    setBusy(null);
    if (res.ok) {
      setNotice(t("decided", { status: t(`status_${res.data.status}` as "status_open") }));
      setDeciding(null);
      setReason("");
      setDocumentId("");
      load();
    } else setError(res.message);
  };

  return (
    <section className={ui.card} data-testid="bank-clarifications">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {notice ? <p className={ui.success}>{notice}</p> : null}
      {rows === null ? <p className="text-sm text-muted">{t("loading")}</p> : null}
      {rows && rows.length === 0 ? <EmptyState title={t("empty")} /> : null}
      {rows && rows.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-2">
          {rows.map((row) => (
            <li key={row.id} className="flex flex-col gap-1 rounded-md border border-border p-3 text-sm" data-testid="clarification-row">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{row.counterpart_name ?? row.bank_transaction_id}</span>
                <span className="tabular-nums">{row.amount ? formatEur(row.amount) : ""}</span>
                <span className="text-muted">{formatDate(row.booking_date)}</span>
                <StatusPill label={t(`status_${row.status}` as "status_open")} variant={row.status === "open" ? "danger" : "gold"} />
                {row.ticket_id ? <span className={ui.badge}>{t("ticket")}</span> : null}
                {row.age_days != null ? (
                  <span className="text-muted" data-testid="clarification-age">
                    {t("age", { days: row.age_days })}
                  </span>
                ) : null}
              </div>
              <p className="text-muted">
                {row.purpose} · {row.reasons.join("; ")}
              </p>
              {canUpdate ? (
                <div className={ui.formActions}>
                  {row.status === "open" ? (
                    <button type="button" className={ui.secondary} disabled={busy === row.id} onClick={() => decide(row, "in_clarification")}>
                      {t("inClarification")}
                    </button>
                  ) : null}
                  {row.status !== "receipt_requested" ? (
                    <button type="button" className={ui.secondary} disabled={busy === row.id} onClick={() => decide(row, "receipt_requested")}>
                      {t("requestReceipt")}
                    </button>
                  ) : null}
                  <button type="button" className={ui.primary} disabled={busy === row.id} onClick={() => setDeciding(deciding === row.id ? null : row.id)}>
                    {t("decide")}
                  </button>
                </div>
              ) : null}
              {deciding === row.id ? (
                <form
                  className="grid gap-2 sm:grid-cols-2"
                  data-testid="clarification-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                  }}
                >
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("reason")}</span>
                    <input className={ui.input} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("documentId")}</span>
                    <input className={ui.input} value={documentId} onChange={(e) => setDocumentId(e.target.value)} />
                  </label>
                  <p className={`${ui.help} sm:col-span-2`}>{t("decideHint")}</p>
                  <div className={`${ui.formActions} sm:col-span-2`}>
                    <button type="button" className={ui.primary} disabled={busy === row.id || reason.trim().length < 3} onClick={() => decide(row, "no_document_required")}>
                      {t("noDocumentRequired")}
                    </button>
                    <button type="button" className={ui.primary} disabled={busy === row.id || documentId.trim().length === 0} onClick={() => decide(row, "resolved")}>
                      {t("resolved")}
                    </button>
                    <button type="button" className={ui.secondary} onClick={() => setDeciding(null)}>
                      {t("cancel")}
                    </button>
                  </div>
                </form>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
