"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Tenant automation switch (`tenant_settings.auto_posting_enabled`, default off), read only.
 *  Switching it on is gated by an open operator decision (plan M12 section 4 item 4, ADR 0013:
 *  whether automation may create comparison postings before G1) and by the runner of step S6,
 *  so the CRM shows the state and does not offer `PUT /banking/automation`. */
export function AutomationSwitchCard() {
  const t = useTranslations("Bank.automation");
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const res = await bff<{ auto_posting_enabled: boolean }>("/api/bff/tenant/settings");
      if (res.ok) setEnabled(Boolean(res.data.auto_posting_enabled));
      else setError(res.message);
    })();
  }, []);

  return (
    <section className={ui.card} data-testid="automation-switch">
      <h2 className={ui.h3}>{t("title")}</h2>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {enabled === null && !error ? <p className="text-sm text-muted">{t("loading")}</p> : null}
      {enabled !== null ? (
        <p className="text-sm" data-testid="automation-state">
          <span className={enabled ? ui.badgeWarning : ui.badge}>{enabled ? t("on") : t("off")}</span>
        </p>
      ) : null}
      <p className={`${ui.help} mt-2`}>{t("gated")}</p>
    </section>
  );
}
