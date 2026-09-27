"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Tenant switch of the Messdienstleister module (master prompt Messdienstleister section 2):
 *  `PATCH /tenant/settings`, field `metering_module_enabled`, default off. Off locks every
 *  write endpoint of the module (403 MHVP-METR-0001); reading stays possible. */
export function MeteringModuleSwitch({ initial, canUpdate }: { initial: boolean; canUpdate: boolean }) {
  const t = useTranslations("MeteringModuleSwitch");
  const [enabled, setEnabled] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle(next: boolean) {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ metering_module_enabled: boolean }>("/api/bff/tenant/settings", {
      method: "PATCH",
      body: JSON.stringify({ metering_module_enabled: next }),
    });
    setBusy(false);
    if (res.ok) {
      setEnabled(res.data.metering_module_enabled);
      setMessage(t("saved"));
    } else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="metering-module-switch-title">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="metering-module-switch-title" className={ui.h2}>
            {t("title")}
          </h2>
          <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${enabled ? "bg-success-bg text-success-fg" : "bg-surface text-muted"}`} data-testid="metering-module-switch-status">
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
        <Link href="/einstellungen/schnittstellen/messdienstleister" className="text-xs underline">
          {t("link")}
        </Link>
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
