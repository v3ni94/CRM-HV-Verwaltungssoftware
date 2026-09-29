import { getTranslations } from "next-intl/server";

import { ConsumptionInfoList } from "@/components/portal/ConsumptionInfoList";
import type { ConsumptionInfoRow } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Verbrauchsinformation (Regel H03, Rolle Mieter): monatliche Verbräuche der eigenen Einheit
 *  aus den Daten des Messdienstes. Erst sichtbar, wenn die Verwaltung die Funktion und die
 *  Vorlage freigegeben hat (403 sonst). Keine Abrechnung, keine Rechtsfolge. */
export default async function ConsumptionInfoPage() {
  const t = await getTranslations("ConsumptionInfo");
  const response = await serverFetch("/api/v1/portal/consumption-info");
  redirectIfUnauthenticated(response);
  if (response.status === 403) {
    return (
      <div className={ui.pageGap}>
        <h1 className={ui.title}>{t("title")}</h1>
        <p className={ui.notice}>{t("locked")}</p>
      </div>
    );
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const rows = (await response.json()) as ConsumptionInfoRow[];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <ConsumptionInfoList rows={rows} />
    </div>
  );
}
