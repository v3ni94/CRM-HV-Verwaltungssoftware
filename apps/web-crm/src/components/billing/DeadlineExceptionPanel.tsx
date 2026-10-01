"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type DeadlineException = {
  deadline_exception: string | null;
  deadline_exception_document_id: string | null;
  deadline_exception_set_at: string | null;
  deadline_exception_effective: boolean;
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** GA06-04 (7.6 A04): reason and evidence document of an exception to the statement deadline.
 *  A late claim stays locked until both are recorded; the legal assessment is the operator's. */
export function DeadlineExceptionPanel({ id, status, initial }: { id: string; status: string; initial: DeadlineException }) {
  const t = useTranslations("Billing.deadlineException");
  const [state, setState] = useState(initial);
  const [reason, setReason] = useState(initial.deadline_exception ?? "");
  const [documentId, setDocumentId] = useState(initial.deadline_exception_document_id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const editable = status === "draft";
  const docValid = documentId.trim() === "" || UUID_RE.test(documentId.trim());

  const save = async () => {
    setBusy(true);
    setError(null);
    const body: Record<string, string | null> = { deadline_exception: reason.trim() || null };
    if (documentId.trim()) body.deadline_exception_document_id = documentId.trim();
    const res = await bff<DeadlineException>(`/api/bff/statements/${id}`, { method: "PATCH", body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) setState(res.data);
    else setError(res.message);
  };

  return (
    <section className="flex flex-col gap-2" aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.help}>{t("hint")}</p>
      <p className={state.deadline_exception_effective ? ui.badge : ui.badgeWarning}>
        {state.deadline_exception_effective ? t("effective") : t("locked")}
      </p>
      {state.deadline_exception_set_at ? <p className="text-sm">{t("setAt", { date: formatDate(state.deadline_exception_set_at.slice(0, 10)) })}</p> : null}
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("reason")}</span>
        <textarea className={ui.input} value={reason} disabled={!editable} onChange={(e) => setReason(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("document")}</span>
        <input className={ui.input} value={documentId} disabled={!editable} onChange={(e) => setDocumentId(e.target.value)} aria-invalid={!docValid} />
      </label>
      {!docValid ? <p className={ui.help}>{t("documentInvalid")}</p> : null}
      {editable ? (
        <button type="button" className={ui.button} onClick={save} disabled={busy || !docValid || reason.trim().length < 3}>
          {t("save")}
        </button>
      ) : (
        <p className={ui.help}>{t("readOnly")}</p>
      )}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
