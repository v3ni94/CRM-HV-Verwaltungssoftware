"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const MODES = ["flag", "first_vote", "proxy_priority", "own_priority"] as const;
type ProxyConflictMode = (typeof MODES)[number];

/** AD06: Mandantenschalter für die Online-Versammlung im Eigentümerportal (Standard aus).
 *  Die Zulässigkeit ist rechtlich offen (AD06-01); das System behauptet sie nicht.
 *  AE31 (AD06-02): Regel für Vollmacht gegen eigene Stimme; Standard "flag" markiert den
 *  Konflikt als Prüfhinweis und verwirft keine Stimme. Ohne `mode` (ältere API) wird die Regel
 *  nicht mitgesendet. */
export function OnlineMeetingSwitch({ enabled, mode }: { enabled: boolean; mode?: string }) {
  const t = useTranslations("HoaWork.onlineSwitch");
  const [value, setValue] = useState(enabled);
  const [rule, setRule] = useState<ProxyConflictMode>(MODES.includes(mode as ProxyConflictMode) ? (mode as ProxyConflictMode) : "flag");
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setState("saving");
    const result = await bff("/api/bff/hoa/online-meeting-settings", {
      method: "PUT",
      body: JSON.stringify(mode === undefined ? { enabled: value } : { enabled: value, proxy_conflict_mode: rule }),
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
    <form onSubmit={save} className={`${ui.card} flex flex-col gap-3`} aria-labelledby="online-switch-title" data-testid="online-meeting-switch">
      <h2 id="online-switch-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className="text-xs text-muted">{t("hint")}</p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={value} onChange={(e) => setValue(e.target.checked)} data-testid="online-enabled" />
        {t("label")}
      </label>
      {mode !== undefined ? (
        <fieldset className="flex flex-col gap-2" data-testid="proxy-conflict-rule">
          <legend className={ui.label}>{t("rule")}</legend>
          <p className="text-xs text-muted">{t("ruleHint")}</p>
          {MODES.map((code) => (
            <label key={code} className="flex items-start gap-2 text-sm">
              <input type="radio" name="proxy-conflict-mode" value={code} checked={rule === code} onChange={() => setRule(code)} data-testid={`rule-${code}`} />
              <span>
                {t(`modes.${code}`)}
                <span className="block text-xs text-muted">{t(`modeHints.${code}`)}</span>
              </span>
            </label>
          ))}
        </fieldset>
      ) : null}
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
