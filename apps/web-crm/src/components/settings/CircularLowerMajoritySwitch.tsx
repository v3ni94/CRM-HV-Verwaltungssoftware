"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Mandantenschalter für den Umlaufbeschluss mit einfacher Mehrheit (M25-02, § 23 Abs. 3 Satz 2
 *  WEG als Einschätzung): `GET/PUT /hoa/circular-lower-majority`, Feld `enabled`, Standard aus.
 *  Das Einschalten ist eine Betreiberentscheidung nach rechtlicher Prüfung; die Zulässigkeit
 *  der abgesenkten Mehrheit im Einzelfall wird von der Plattform nicht behauptet. */
export function CircularLowerMajoritySwitch({ initial, canUpdate }: { initial: boolean; canUpdate: boolean }) {
  const t = useTranslations("CircularLowerMajoritySwitch");
  const [enabled, setEnabled] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle(next: boolean) {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ enabled: boolean }>("/api/bff/hoa/circular-lower-majority", {
      method: "PUT",
      body: JSON.stringify({ enabled: next }),
    });
    setBusy(false);
    if (res.ok) {
      setEnabled(res.data.enabled);
      setMessage(t("saved"));
    } else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="circular-lower-majority-switch-title">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="circular-lower-majority-switch-title" className={ui.h2}>
            {t("title")}
          </h2>
          <span
            className={`rounded-md px-2 py-0.5 text-xs font-medium ${enabled ? "bg-success-bg text-success-fg" : "bg-surface text-muted"}`}
            data-testid="circular-lower-majority-switch-status"
          >
            {enabled ? t("status.on") : t("status.off")}
          </span>
        </div>
        <p className={ui.help}>{t("description")}</p>
        <p className="text-xs text-warning-fg">{t("risk")}</p>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} disabled={!canUpdate || busy} onChange={(e) => void toggle(e.target.checked)} />
          <span>{t("label")}</span>
        </label>
        {!canUpdate ? <p className={ui.help}>{t("readOnly")}</p> : null}
        {message ? <span className="text-xs text-success-fg">{message}</span> : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
