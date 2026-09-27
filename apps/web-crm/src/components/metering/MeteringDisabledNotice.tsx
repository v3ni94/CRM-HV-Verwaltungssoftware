import Link from "next/link";
import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

/** Shown wherever the module is reached while tenant_settings.metering_module_enabled is
 *  false (section 2). Read views stay reachable, write actions are refused by the API
 *  (MHVP-METR-0001); the notice points to the tenant settings. */
export function MeteringDisabledNotice() {
  const t = useTranslations("Metering.disabled");
  return (
    <div className={ui.notice} role="status" data-testid="metering-disabled">
      <p>{t("text")}</p>
      <Link href="/einstellungen/mandant" className="mt-1 inline-block text-sm font-medium underline">
        {t("link")}
      </Link>
    </div>
  );
}
