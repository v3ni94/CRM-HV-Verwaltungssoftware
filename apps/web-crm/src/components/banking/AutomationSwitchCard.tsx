"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type SwitchSettings = { auto_posting_enabled: boolean; auto_posting_outgoing_enabled?: boolean };

/** Tenant automation switches (`auto_posting_enabled`, `auto_posting_outgoing_enabled`, both
 *  default off), shown read only. Switching on runs only through the four eyes request with
 *  open G1 on the automation settings page (AE03, AF01): `PUT /banking/automation` no longer
 *  switches on. The outgoing switch has an effect only while the main switch is on. */
export function AutomationSwitchCard() {
  const t = useTranslations("Bank.automation");
  const [state, setState] = useState<SwitchSettings | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const res = await bff<SwitchSettings>("/api/bff/tenant/settings");
      if (res.ok) setState(res.data);
      else setError(res.message);
    })();
  }, []);

  const enabled = state ? Boolean(state.auto_posting_enabled) : null;
  const outgoing = state ? Boolean(state.auto_posting_outgoing_enabled) : null;

  return (
    <section className={ui.card} data-testid="automation-switch">
      <h2 className={ui.h3}>{t("title")}</h2>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {state === null && !error ? <p className="text-sm text-muted">{t("loading")}</p> : null}
      {state !== null ? (
        <p className="text-sm" data-testid="automation-state">
          <span className={enabled ? ui.badgeWarning : ui.badge}>{enabled ? t("on") : t("off")}</span>{" "}
          <span className={outgoing ? ui.badgeWarning : ui.badge} data-testid="automation-outgoing-state">
            {outgoing ? t("outgoingOn") : t("outgoingOff")}
          </span>
        </p>
      ) : null}
      <p className={`${ui.help} mt-2`}>{t("gated")}</p>
      <p className={`${ui.help} mt-2`}>
        {t("requestPath")}{" "}
        <Link href="/einstellungen/buchhaltung/automatik" className="underline">
          {t("requestLink")}
        </Link>
      </p>
    </section>
  );
}
