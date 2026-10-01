"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Automation = {
  rent_increase_check: boolean;
  batch_mail_classification: boolean;
  provider_released: boolean;
  blocked_reason: string | null;
};

/** Schalter der automatischen KI-Läufe (R09): Mieterhöhungsprüfung beim Anlegen oder Ändern
 *  eines Falls und nächtliche Klassifikation von Mails ohne Vorschlag. Standard aus; die
 *  Anbieterfreigabe bleibt davon unberührt. */
export function AiAutomationSwitches() {
  const t = useTranslations("AiAutomation");
  const [state, setState] = useState<Automation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void bff<Automation>("/api/bff/ai/automation").then((res) => {
      if (res.ok) setState(res.data);
      else setError(res.message);
    });
  }, []);

  const change = async (patch: Partial<Pick<Automation, "rent_increase_check" | "batch_mail_classification">>) => {
    setBusy(true);
    setError(null);
    const res = await bff<Automation>("/api/bff/ai/automation", { method: "PUT", body: JSON.stringify(patch) });
    setBusy(false);
    if (res.ok) setState(res.data);
    else setError(res.message);
  };

  return (
    <section className={`${ui.card} flex flex-col gap-2`} aria-labelledby="ai-automation-title">
      <h2 id="ai-automation-title" className="text-sm font-semibold">{t("title")}</h2>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={state?.rent_increase_check ?? false}
          disabled={busy || !state}
          onChange={(e) => void change({ rent_increase_check: e.target.checked })}
        />
        {t("rentIncrease")}
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={state?.batch_mail_classification ?? false}
          disabled={busy || !state}
          onChange={(e) => void change({ batch_mail_classification: e.target.checked })}
        />
        {t("batchMail")}
      </label>
      <p className="text-xs text-muted">{t("hint")}</p>
      {state && !state.provider_released ? (
        <p className="text-xs text-muted">{t("noProvider", { reason: state.blocked_reason ?? "-" })}</p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
