"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type ProtocolEntry = {
  type: string;
  occurred_at: string;
  payload: { file_sha256?: string; reference?: string; channel?: string };
};

/** Lastschriftlauf (M15, pain.008, Folgepunkt M15-01): Freigabe durch zwei verschiedene
 *  Personen, Verwerfen, Datei als Dokument ablegen, Download mit Prüfsumme und Protokoll sowie
 *  Bestätigung der Einreichung bei der Bank. Download und Einreichung sperrt die API selbst
 *  hinter G2; ein Versuch bei geschlossenem Gate zeigt hier nur die Fehlermeldung an. */
export function DirectDebitRunActions({
  id,
  status,
  approvals,
}: {
  id: string;
  status: string;
  approvals: number;
}) {
  const t = useTranslations("DirectDebits");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [protocol, setProtocol] = useState<ProtocolEntry[] | null>(null);
  const [reference, setReference] = useState("");
  const [preNotified, setPreNotified] = useState<number | null>(null);
  const act = async (action: "approve" | "cancel" | "file") => {
    if (action === "cancel" && !window.confirm(t("confirmCancel"))) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/accounting/direct-debits/${id}/${action}`, { method: "POST" });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
  };
  const loadProtocol = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<ProtocolEntry[]>(`/api/bff/accounting/direct-debits/${id}/downloads`);
    setBusy(false);
    if (res.ok) setProtocol(res.data);
    else setError(res.message);
  };
  const download = () => {
    window.open(`/api/bff/accounting/direct-debits/${id}/file`, "_blank", "noopener");
    void loadProtocol();
  };
  const submit = async () => {
    if (!reference.trim()) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/accounting/direct-debits/${id}/submit`, {
      method: "POST",
      body: JSON.stringify({ reference: reference.trim() }),
    });
    setBusy(false);
    if (res.ok) {
      router.refresh();
      void loadProtocol();
    } else setError(res.message);
  };
  // AF03 (GAF-04): Vorabinformationen je Zahler als Entwurf (nur Dokumente, kein Versand).
  const preNotify = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<unknown[]>(`/api/bff/accounting/direct-debits/${id}/pre-notifications`, { method: "POST" });
    setBusy(false);
    if (res.ok) setPreNotified(res.data.length);
    else setError(res.message);
  };
  const canPreNotify = status === "draft" || status === "approved" || status === "file_generated";
  const canApprove = status === "draft";
  const canFile = status === "approved" && approvals >= 2;
  const canCancel = status === "draft" || status === "approved" || status === "file_generated";
  const canDownload = status === "file_generated" || status === "exported";
  const submitted = protocol?.some((e) => e.type === "direct_debit_run.submitted") ?? false;
  if (!canApprove && !canFile && !canCancel && !canDownload) return null;
  return (
    <span className="inline-flex flex-col gap-1">
      <span className="flex flex-wrap gap-2">
        {canApprove ? (
          <button type="button" className={ui.button} onClick={() => act("approve")} disabled={busy}>
            {t("approve")}
          </button>
        ) : null}
        {canFile ? (
          <button type="button" className={ui.button} onClick={() => act("file")} disabled={busy}>
            {t("generateFile")}
          </button>
        ) : null}
        {canDownload ? (
          <button type="button" className={ui.button} onClick={download} disabled={busy}>
            {t("download")}
          </button>
        ) : null}
        {canDownload ? (
          <button type="button" className={ui.button} onClick={loadProtocol} disabled={busy}>
            {t("showProtocol")}
          </button>
        ) : null}
        {canPreNotify ? (
          <button type="button" className={ui.button} onClick={preNotify} disabled={busy}>
            {t("preNotify")}
          </button>
        ) : null}
        {canCancel ? (
          <button type="button" className={ui.button} onClick={() => act("cancel")} disabled={busy}>
            {t("cancel")}
          </button>
        ) : null}
      </span>
      {canDownload && !submitted ? (
        <span className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            className={ui.input}
            placeholder={t("submitReferencePlaceholder")}
            value={reference}
            onChange={(e) => setReference(e.target.value)}
          />
          <button type="button" className={ui.button} onClick={submit} disabled={busy || !reference.trim()}>
            {t("confirmSubmission")}
          </button>
        </span>
      ) : null}
      {preNotified !== null ? (
        <span role="status" className="text-xs text-muted">
          {t("preNotified", { n: preNotified })}
        </span>
      ) : null}
      {protocol ? (
        <ul className="text-xs text-muted">
          {protocol.length === 0 ? (
            <li>{t("protocolEmpty")}</li>
          ) : (
            protocol.map((e, i) => (
              <li key={i}>
                {e.type === "direct_debit_run.file_downloaded"
                  ? t("protocolDownload", { date: e.occurred_at, sha: e.payload.file_sha256 ?? "" })
                  : t("protocolSubmitted", { date: e.occurred_at, reference: e.payload.reference ?? "" })}
              </li>
            ))
          )}
        </ul>
      ) : null}
      {error ? (
        <span role="alert" className={ui.error}>
          {error}
        </span>
      ) : null}
    </span>
  );
}
