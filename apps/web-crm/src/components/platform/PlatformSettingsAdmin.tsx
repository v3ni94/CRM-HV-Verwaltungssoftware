"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type PlatformSettings = { gate_superadmin_bypass: boolean; version: number };

/** AG03 (GAF-11): mask for `GET/PATCH /platform/settings` (platform administrators). The only
 *  switch, `gate_superadmin_bypass`, weakens the four eyes control of the release gates and
 *  stays off by default; it opens no gate itself. */
export function PlatformSettingsAdmin() {
  const t = useTranslations("AG03");
  const [settings, setSettings] = useState<PlatformSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void bff<PlatformSettings>("/api/bff/platform/settings").then((res) => {
      if (!alive) return;
      if (res.ok) setSettings(res.data);
      else setError(res.message || t("loadFailed"));
    });
    return () => {
      alive = false;
    };
  }, [t]);

  async function toggle() {
    if (!settings || !window.confirm(t("confirm"))) return;
    setBusy(true);
    setError(null);
    const res = await bff<PlatformSettings>("/api/bff/platform/settings", {
      method: "PATCH",
      body: JSON.stringify({ gate_superadmin_bypass: !settings.gate_superadmin_bypass }),
    });
    setBusy(false);
    if (res.ok) setSettings(res.data);
    else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="platform-settings-title">
      <h2 id="platform-settings-title" className={ui.h2}>
        {t("platformTitle")}
      </h2>
      <p className="text-sm text-muted">{t("platformHint")}</p>
      {settings ? (
        <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
          <span>{t("bypassLabel")}:</span>
          <strong>{settings.gate_superadmin_bypass ? t("on") : t("off")}</strong>
          <span className="text-xs text-muted">{t("version", { version: settings.version })}</span>
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void toggle()}>
            {settings.gate_superadmin_bypass ? t("off") : t("on")}
          </button>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
