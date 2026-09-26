"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type JobSettings = {
  digest_mail_enabled: boolean;
  deadline_lead_days: number;
  deadline_lead_days_default: number;
};

/** Tenant switches of the daily jobs (A40, A41): lead time of the deadline list and the
 *  optional digest mail (default off). Saving needs tenant_settings:update (checked server side). */
export function JobSettingsForm({ initial }: { initial: JobSettings }) {
  const t = useTranslations("Deadlines");
  const [leadDays, setLeadDays] = useState(String(initial.deadline_lead_days));
  const [mail, setMail] = useState(initial.digest_mail_enabled);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setState("saving");
    const result = await bff<JobSettings>("/api/bff/workspace/job-settings", {
      method: "PUT",
      body: JSON.stringify({ digest_mail_enabled: mail, deadline_lead_days: Number(leadDays) }),
    });
    if (result.ok) {
      setState("saved");
      setMessage(null);
      setLeadDays(String(result.data.deadline_lead_days));
      setMail(result.data.digest_mail_enabled);
    } else {
      setState("error");
      setMessage(result.message);
    }
  }

  return (
    <form onSubmit={save} className={`${ui.card} flex flex-col gap-3`} aria-labelledby="job-settings-title">
      <h2 id="job-settings-title" className={ui.h2}>
        {t("settings.title")}
      </h2>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("settings.leadDays", { default: initial.deadline_lead_days_default })}</span>
        <input
          className={`${ui.input} sm:w-40`}
          type="number"
          min={0}
          max={730}
          value={leadDays}
          onChange={(e) => setLeadDays(e.target.value)}
          data-testid="lead-days"
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={mail} onChange={(e) => setMail(e.target.checked)} data-testid="digest-mail" />
        {t("settings.digestMail")}
      </label>
      <div className={ui.formActions}>
        <button type="submit" className={ui.primary} disabled={state === "saving"}>
          {t("settings.save")}
        </button>
      </div>
      {state === "saved" ? <p className={ui.success}>{t("settings.saved")}</p> : null}
      {state === "error" ? (
        <p role="alert" className={ui.alert}>
          {message ?? t("settings.error")}
        </p>
      ) : null}
    </form>
  );
}
