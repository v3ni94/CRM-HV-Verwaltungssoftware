"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Einheitliches Statusmodell der Abrechnungsobjekte (6.9.3, S69-01). Spiegelt die
 *  Übergangstabelle der API; die API bleibt maßgeblich (Vier-Augen, Freigabestufen, Beschluss). */
export const STATEMENT_STATUSES = [
  "draft",
  "calculated",
  "internally_approved",
  "board_reviewed",
  "resolved",
  "issued",
  "due",
  "posted",
  "locked",
] as const;
export type StatementStatusValue = (typeof STATEMENT_STATUSES)[number];
export type StatusLogEntry = { from: string; to: string; by: string | null; at: string; note: string | null };

const NEXT: Record<StatementStatusValue, StatementStatusValue[]> = {
  draft: [],
  calculated: ["internally_approved"],
  internally_approved: ["board_reviewed", "resolved", "issued"],
  board_reviewed: ["resolved", "issued"],
  resolved: ["issued"],
  issued: ["due"],
  due: ["posted"],
  posted: ["locked"],
  locked: [],
};

/** Ziele ab ``status``: ohne ``resolved`` außerhalb der WEG; in der WEG ``issued`` erst nach dem Beschluss. */
export function nextTargets(status: StatementStatusValue, hoa: boolean): StatementStatusValue[] {
  return (NEXT[status] ?? []).filter((t) => (hoa ? t !== "issued" || status === "resolved" : t !== "resolved"));
}

export function StatementStatusActions<T>({
  url,
  status,
  hoa,
  gate,
  log = [],
  onChanged,
}: {
  url: string;
  status: StatementStatusValue;
  hoa: boolean;
  gate: "G3" | "G4";
  log?: StatusLogEntry[];
  onChanged: (data: T) => void;
}) {
  const t = useTranslations("StatementStatus");
  const [note, setNote] = useState("");
  const [entries, setEntries] = useState("");
  const [resolution, setResolution] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const targets = nextTargets(status, hoa);

  const move = async (target: StatementStatusValue) => {
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = { target };
    if (note.trim()) body.note = note.trim();
    if (target === "posted") body.entry_ids = entries.split(/[\s,;]+/).filter(Boolean);
    if (target === "resolved" && resolution.trim()) body.resolution_id = resolution.trim();
    const res = await bff<T>(`${url}/transition`, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) {
      setNote("");
      onChanged(res.data);
    } else setError(res.message);
  };

  return (
    <div className="mt-3 flex flex-col gap-2" data-testid="statement-status-actions">
      {targets.length ? (
        <>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("note")}</span>
              <input className={ui.input} value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} />
            </label>
            {targets.includes("resolved") ? (
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("resolutionId")}</span>
                <input className={ui.input} value={resolution} onChange={(e) => setResolution(e.target.value)} />
              </label>
            ) : null}
            {targets.includes("posted") ? (
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("entryIds")}</span>
                <input className={ui.input} value={entries} onChange={(e) => setEntries(e.target.value)} />
              </label>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {targets.map((target) => (
              <button key={target} type="button" className={ui.secondary} disabled={busy} onClick={() => move(target)}>
                {t(`to.${target}`)}
              </button>
            ))}
          </div>
        </>
      ) : null}
      <p className={ui.help}>{t("gateHint", { gate })}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <h4 className="text-sm font-medium">{t("logTitle")}</h4>
      {log.length === 0 ? <p className="text-sm text-muted">{t("logEmpty")}</p> : null}
      {log.length ? (
        <ul className="flex flex-col gap-1 text-sm" aria-label={t("log")}>
          {log.map((e, i) => (
            <li key={`${e.at}-${i}`}>
              {formatDateTime(e.at)}: {t(`status.${e.from as StatementStatusValue}`)} {t("arrow")} {t(`status.${e.to as StatementStatusValue}`)}
              {e.note ? `, ${e.note}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
