"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Setting = { weekly_preview_enabled: boolean; schedule: string };

/** GAF-09: Einstellung der wöchentlichen Zahllauf-Vorschau (nur Entwurf, keine Zahlung). Ändern
 *  nur mit tenant_settings:update, sonst Anzeige. */
export function PaymentRunSettingsCard({ canUpdate }: { canUpdate: boolean }) {
  const t = useTranslations("PaymentRunSettings");
  const [setting, setSetting] = useState<Setting | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void bff<Setting>("/api/bff/accounting/payment-runs/settings").then((res) => {
      if (res.ok) setSetting(res.data);
      else setError(res.message);
    });
  }, []);

  async function toggle(next: boolean) {
    setBusy(true);
    setError(null);
    const res = await bff<Setting>("/api/bff/accounting/payment-runs/settings", {
      method: "PUT",
      body: JSON.stringify({ weekly_preview_enabled: next }),
    });
    setBusy(false);
    if (res.ok) setSetting(res.data);
    else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="pr-settings-title" data-testid="payment-run-settings">
      <h2 id="pr-settings-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className={ui.help}>{t("help")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {setting ? (
        <label className="mt-2 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={setting.weekly_preview_enabled}
            disabled={!canUpdate || busy}
            onChange={(e) => void toggle(e.target.checked)}
          />
          {t("weekly", { schedule: setting.schedule })}
        </label>
      ) : null}
      {!canUpdate ? <p className={ui.help}>{t("noRight")}</p> : null}
    </section>
  );
}
