"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Mandanteneinstellung Einladungsfrist in Wochen (Entwurfswert 3, zu prüfen) und Schalter für
 *  virtuelle Versammlungen (V13, Standard aus). Keine Rechtsbehauptung; die Prüfung beim Versand
 *  warnt und verlangt einen dokumentierten Grund. */
export function MeetingSettings({
  weeks,
  virtualEnabled,
  termLockEnabled = false,
  transitionDate = null,
}: {
  weeks: number;
  virtualEnabled: boolean;
  /** GA07-01: Sperre bei Geltungsdauer über drei Jahre, Standard aus (nur Hinweis). */
  termLockEnabled?: boolean;
  /** AE12: Stichtag der Übergangsregel, vom Betreiber eingetragen (kein Rechtstext, keine Sperrwirkung). */
  transitionDate?: string | null;
}) {
  const t = useTranslations("HoaWork.meetingSettings");
  const [value, setValue] = useState(String(weeks));
  const [virtual, setVirtual] = useState(virtualEnabled);
  const [termLock, setTermLock] = useState(termLockEnabled);
  const [transition, setTransition] = useState(transitionDate ?? "");
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const n = Number.parseInt(value, 10);
    if (!Number.isFinite(n) || n < 1 || n > 12) {
      setState("error");
      setMessage(t("weeksInvalid"));
      return;
    }
    setState("saving");
    const result = await bff("/api/bff/hoa/meeting-settings", {
      method: "PUT",
      body: JSON.stringify({ invitation_weeks: n, virtual_meetings_enabled: virtual, virtual_basis_term_lock_enabled: termLock, virtual_basis_transition_date: transition || null }),
    });
    if (result.ok) {
      setState("saved");
      setMessage(null);
    } else {
      setState("error");
      setMessage(result.message);
    }
  }

  return (
    <form onSubmit={save} className={`${ui.card} flex flex-col gap-3`} aria-labelledby="meeting-settings-title" data-testid="meeting-settings">
      <h2 id="meeting-settings-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className="text-xs text-muted">{t("hint")}</p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("weeks")}</span>
        <input className={`${ui.input} sm:w-32`} type="number" min={1} max={12} value={value} onChange={(e) => setValue(e.target.value)} data-testid="invitation-weeks" />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={virtual} onChange={(e) => setVirtual(e.target.checked)} data-testid="virtual-enabled" />
        {t("virtual")}
      </label>
      <p className="text-xs text-muted">{t("virtualHint")}</p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={termLock} onChange={(e) => setTermLock(e.target.checked)} data-testid="virtual-term-lock" />
        {t("termLock")}
      </label>
      <p className="text-xs text-muted">{t("termLockHint")}</p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("transitionDate")}</span>
        <input className={`${ui.input} sm:w-48`} type="date" value={transition} onChange={(e) => setTransition(e.target.value)} data-testid="virtual-transition-date" />
      </label>
      <p className="text-xs text-muted">{t("transitionHint")}</p>
      <div className={ui.formActions}>
        <button type="submit" className={ui.primary} disabled={state === "saving"}>
          {t("save")}
        </button>
      </div>
      {state === "saved" ? <p className={ui.success}>{t("saved")}</p> : null}
      {state === "error" && message ? (
        <p role="alert" className={ui.alert}>
          {message}
        </p>
      ) : null}
    </form>
  );
}
