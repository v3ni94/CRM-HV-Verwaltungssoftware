"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Erledigungsnotiz beim Abschluss (Betreiberauftrag 26.09.2026, Entscheidung M19-04 vom
 *  26.09.2026): Art aus der je Mandant wirksamen Liste (`GET /tickets/resolution-kinds`:
 *  aktive eingebaute und eigene Arten) plus Freitext, Pflicht bei "sonstiges". Die API
 *  verlangt sie für done, closed und rejected. */
export type ResolutionKindOption = { code: string; label: string; builtin: boolean; active: boolean };

export const CLOSING_STATUSES = ["done", "closed", "rejected"] as const;

export type Resolution = { kind: string; note: string | null };

export function isClosingStatus(status: string): boolean {
  return (CLOSING_STATUSES as readonly string[]).includes(status);
}

export async function loadResolutionKinds(): Promise<ResolutionKindOption[] | null> {
  const res = await bff<{ kinds: ResolutionKindOption[] }>("/api/bff/tickets/resolution-kinds");
  return res.ok ? res.data.kinds : null;
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
  const [kinds, setKinds] = useState<ResolutionKindOption[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [kind, setKind] = useState<string>(status === "rejected" ? "abgelehnt" : "");
  const [note, setNote] = useState("");

  useEffect(() => {
    let cancelled = false;
    void loadResolutionKinds().then((list) => {
      if (cancelled) return;
      if (list === null) setLoadError(true);
      else setKinds(list.filter((k) => k.active));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const options = kinds ?? [];
  // "abgelehnt" is preselected for rejected; when the tenant disabled it the user chooses.
  const effectiveKind = kinds && kind !== "" && !options.some((k) => k.code === kind) ? "" : kind;
  const noteRequired = effectiveKind === "sonstiges";
  const valid = effectiveKind !== "" && (!noteRequired || note.trim() !== "");
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
      {loadError ? (
        <p role="alert" className={ui.alert}>
          {t("resolution.loadError")}
        </p>
      ) : null}
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("resolution.kind")}</span>
        <select className={ui.input} value={effectiveKind} disabled={kinds === null} onChange={(e) => setKind(e.target.value)}>
          <option value="">{kinds === null && !loadError ? t("resolution.loading") : t("resolution.choose")}</option>
          {options.map((k) => (
            <option key={k.code} value={k.code}>
              {k.label}
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
          onClick={() => onConfirm({ kind: effectiveKind, note: note.trim() || null })}
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
