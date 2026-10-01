"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

import { DeletionChecklist } from "./DeletionChecklist";

export type TrashEntry = {
  document_id: string;
  title: string;
  filename: string;
  deleted_at: string;
  deleted_by: string | null;
  purge_at: string;
  days_left: number;
  status: "in_trash" | "due" | "held";
  blocker: string | null;
};

type Acting = { id: string; kind: "restore" | "purge" };

/** Papierkorb (AE33, AC07-03): gelöschte Dokumente, Wiederherstellung und vorzeitige endgültige
 *  Löschung mit Begründung (beides protokolliert). Eine Sperre hält das Dokument im Papierkorb;
 *  die endgültige Löschung prüft Sperren und Fristen jedes Mal erneut. */
export function DocumentTrash({ entries: initial, canDelete }: { entries: TrashEntry[]; canDelete: boolean }) {
  const t = useTranslations("DocumentTrash");
  const [entries, setEntries] = useState(initial);
  const [acting, setActing] = useState<Acting | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!acting) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const result = await bff<unknown>(`/api/bff/documents/trash/${acting.id}/${acting.kind}`, {
      method: "POST",
      body: JSON.stringify({ reason: reason.trim() }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setEntries((list) => list.filter((e) => e.document_id !== acting.id));
    setMessage(t(acting.kind === "restore" ? "restored" : "purged"));
    setActing(null);
    setReason("");
  }

  if (entries.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        {message ? <p role="status" className={ui.success}>{message}</p> : null}
        <EmptyState title={t("empty")} />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <p className={ui.notice}>{t("rules")}</p>
      {message ? <p role="status" className={ui.success}>{message}</p> : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      <ul className="flex flex-col gap-3">
        {entries.map((e) => (
          <li key={e.document_id} className={ui.card}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="font-semibold">{e.title}</h3>
              <span className={ui.help}>{t(`status.${e.status}`)}</span>
            </div>
            <p className={ui.help}>{e.filename}</p>
            <p className="mt-1 text-sm">
              {t("deletedAt", { at: formatDateTime(e.deleted_at) })}
              {" · "}
              {t("purgeAt", { at: formatDate(e.purge_at), days: e.days_left })}
            </p>
            {e.blocker ? <p className={`${ui.alert} mt-2`}>{t("blocked", { reason: e.blocker })}</p> : null}
            {canDelete ? (
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  className={ui.button}
                  disabled={busy}
                  onClick={() => {
                    setActing({ id: e.document_id, kind: "restore" });
                    setReason("");
                  }}
                >
                  {t("restore")}
                </button>
                <button
                  type="button"
                  className={ui.danger}
                  disabled={busy || e.status === "held"}
                  onClick={() => {
                    setActing({ id: e.document_id, kind: "purge" });
                    setReason("");
                  }}
                >
                  {t("purge")}
                </button>
              </div>
            ) : null}
            {acting?.id === e.document_id ? (
              <div className="mt-2 flex flex-col gap-2">
                <label className={ui.label} htmlFor={`trash-reason-${e.document_id}`}>
                  {t("reasonLabel")}
                </label>
                <input
                  id={`trash-reason-${e.document_id}`}
                  className={ui.input}
                  value={reason}
                  maxLength={500}
                  onChange={(event) => setReason(event.target.value)}
                />
                {acting.kind === "purge" ? <p className={ui.help}>{t("purgeConfirm")}</p> : null}
                <div className="flex gap-2">
                  <button
                    type="button"
                    className={acting.kind === "purge" ? ui.danger : ui.primary}
                    disabled={busy || reason.trim().length < 3}
                    onClick={() => void submit()}
                  >
                    {t(acting.kind === "restore" ? "confirmRestore" : "confirmPurge")}
                  </button>
                  <button type="button" className={ui.button} disabled={busy} onClick={() => setActing(null)}>
                    {t("cancel")}
                  </button>
                </div>
              </div>
            ) : null}
            <div className="mt-2">
              <DeletionChecklist documentId={e.document_id} canDelete={false} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
