import { getTranslations } from "next-intl/server";

import { StaffProtocolList, type StaffProtocol } from "@/components/handover/StaffProtocolList";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Übergabeprotokolle für Mitarbeiter (M2-08 Rest, 26.09.2026): jedes Protokoll des Mandanten
 *  mit Objekt, Einheit, Datum, Status und PDF, nur lesend über /api/v1/portal/handover-protocols.
 *  Ohne das Portalrecht handover:read antwortet die Schnittstelle mit 403; die Seite zeigt dann
 *  einen Hinweis statt einer Liste. */
export default async function StaffHandoverPage() {
  const t = await getTranslations("HandoverStaff");
  const response = await serverFetch("/api/v1/portal/handover-protocols");
  redirectIfUnauthenticated(response);
  if (response.status === 403) {
    return (
      <div className={ui.pageGap}>
        <h1 className={ui.title}>{t("title")}</h1>
        <p className={ui.notice}>{t("forbidden")}</p>
      </div>
    );
  }
  if (!response.ok) throw new Error(`portal/handover-protocols: ${response.status}`);
  const rows = (await response.json()) as StaffProtocol[];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <p className="text-sm text-muted">{t("intro")}</p>
      <StaffProtocolList rows={rows} />
    </div>
  );
}
