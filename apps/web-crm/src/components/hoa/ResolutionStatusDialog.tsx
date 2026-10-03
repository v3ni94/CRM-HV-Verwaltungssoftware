"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const STATUSES = ["contested", "annulled", "legally_binding", "void"] as const;

/**
 * GAM-201 (D54): status dialog per resolution. Writes the effectiveness status and the court
 * note (court, file number, date, reason) through PATCH /hoa/resolutions/{id}. The change
 * cancels nothing: dependent plans, levies and statements stay as they are (API only reports).
 */
export function ResolutionStatusDialog({ resolutionId, currentNotes }: { resolutionId: string; currentNotes?: string | null }) {
  const t = useTranslations("ResolutionStatus");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<string>("contested");
  const [court, setCourt] = useState("");
  const [fileNumber, setFileNumber] = useState("");
  const [courtDate, setCourtDate] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const valid = reason.trim().length >= 3;

  const save = async () => {
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    const parts = [
      `${t("statuses." + status)}`,
      court.trim() ? `${t("court")}: ${court.trim()}` : "",
      fileNumber.trim() ? `${t("fileNumber")}: ${fileNumber.trim()}` : "",
      courtDate ? `${t("courtDate")}: ${courtDate}` : "",
      `${t("reason")}: ${reason.trim()}`,
    ].filter(Boolean);
    const notes = [currentNotes?.trim() ?? "", parts.join(", ")].filter(Boolean).join("\n");
    const res = await bff(`/api/bff/hoa/resolutions/${resolutionId}`, { method: "PATCH", body: JSON.stringify({ status, court_notes: notes }) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setSaved(true);
    setOpen(false);
    router.refresh();
  };

  if (!open) {
    return (
      <span className="block" data-testid={`resolution-status-${resolutionId}`}>
        <button type="button" className={ui.buttonSm} onClick={() => setOpen(true)}>
          {t("open")}
        </button>
        {saved ? (
          <span role="status" className={ui.success}>
            {t("saved")}
          </span>
        ) : null}
      </span>
    );
  }
  return (
    <div className="mt-1 flex flex-col gap-2 rounded border p-2" role="group" aria-label={t("title")} data-testid={`resolution-status-${resolutionId}`}>
      <p className={ui.subtitle}>{t("title")}</p>
      <p className={ui.help}>{t("hint")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("status")}</span>
          <select className={ui.input} value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`statuses.${s}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("court")}</span>
          <input className={ui.input} value={court} onChange={(e) => setCourt(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("fileNumber")}</span>
          <input className={ui.input} value={fileNumber} onChange={(e) => setFileNumber(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("courtDate")}</span>
          <input type="date" className={ui.input} value={courtDate} onChange={(e) => setCourtDate(e.target.value)} />
        </label>
      </div>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("reason")}</span>
        <textarea className={ui.input} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      {!valid && reason ? <p className={ui.help}>{t("missing")}</p> : null}
      <div className={ui.formActions}>
        <button type="button" className={ui.primary} onClick={() => void save()} disabled={!valid || busy} aria-busy={busy}>
          {t("save")}
        </button>
        <button type="button" className={ui.button} onClick={() => setOpen(false)}>
          {t("cancel")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
