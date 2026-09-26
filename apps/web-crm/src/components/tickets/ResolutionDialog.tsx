"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { ui } from "@/lib/ui";

/** Erledigungsnotiz beim Abschluss (Betreiberauftrag 26.09.2026): Art aus fester Liste plus
 *  Freitext, Pflicht bei "sonstiges". Die API verlangt sie für done, closed und rejected. */
export const RESOLUTION_KINDS = [
  "stammdaten_ergaenzt",
  "handwerker_beauftragt",
  "auskunft_erteilt",
  "weitergeleitet",
  "kein_handlungsbedarf",
  "abgelehnt",
  "sonstiges",
] as const;

export const CLOSING_STATUSES = ["done", "closed", "rejected"] as const;

export type Resolution = { kind: string; note: string | null };

export function isClosingStatus(status: string): boolean {
  return (CLOSING_STATUSES as readonly string[]).includes(status);
}

export function ResolutionDialog({
  status,
  count,
  busy,
  onConfirm,
  onCancel,
}: {
  status: string;
  count?: number;
  busy?: boolean;
  onConfirm: (resolution: Resolution) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("Tickets");
  const [kind, setKind] = useState<string>(status === "rejected" ? "abgelehnt" : "");
  const [note, setNote] = useState("");
  const noteRequired = kind === "sonstiges";
  const valid = kind !== "" && (!noteRequired || note.trim() !== "");
  return (
    <section
      role="dialog"
      aria-modal="false"
      aria-labelledby="ticket-resolution-title"
      className={`${ui.card} flex flex-col gap-3`}
      data-testid="resolution-dialog"
    >
      <h2 id="ticket-resolution-title" className={ui.h2}>
        {t("resolution.title", { status: t(`statuses.${status}`) })}
      </h2>
      <p className="text-sm text-muted">{count && count > 1 ? t("resolution.hintBulk", { count }) : t("resolution.hint")}</p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("resolution.kind")}</span>
        <select className={ui.input} value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">{t("resolution.choose")}</option>
          {RESOLUTION_KINDS.map((k) => (
            <option key={k} value={k}>
              {t(`resolution.kinds.${k}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{noteRequired ? t("resolution.noteRequired") : t("resolution.note")}</span>
        <textarea className={ui.input} rows={3} maxLength={4000} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <div className={ui.formActions}>
        <button
          type="button"
          className={ui.primary}
          disabled={busy || !valid}
          onClick={() => onConfirm({ kind, note: note.trim() || null })}
        >
          {t("resolution.confirm")}
        </button>
        <button type="button" className={ui.secondary} disabled={busy} onClick={onCancel}>
          {t("resolution.cancel")}
        </button>
      </div>
    </section>
  );
}
