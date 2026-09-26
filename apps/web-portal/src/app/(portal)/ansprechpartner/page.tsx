import { getTranslations } from "next-intl/server";

import { PropertyContactList } from "@/components/portal/PropertyContactList";
import type { PropertyContacts } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Ansprechpartner des Objekts (A51, Rolle Eigentümer): Verwaltung, Hausmeister und
 *  Notdienst aus den Stammdaten, soweit für Eigentümer freigegeben. */
export default async function PropertyContactsPage() {
  const t = await getTranslations("Contacts");
  const response = await serverFetch("/api/v1/portal/property-contacts");
  redirectIfUnauthenticated(response);
  if (response.status === 403) {
    return (
      <div className={ui.pageGap}>
        <h1 className={ui.title}>{t("title")}</h1>
        <p className={ui.notice}>{t("ownersOnly")}</p>
      </div>
    );
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const rows = (await response.json()) as PropertyContacts[];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <PropertyContactList rows={rows} />
    </div>
  );
}
