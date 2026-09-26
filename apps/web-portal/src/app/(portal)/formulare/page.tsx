import { getTranslations } from "next-intl/server";

import { PortalForms } from "@/components/portal/PortalForms";
import type { PortalForm } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Formulare (A56): von der Verwaltung bereitgestellte Formulare für die eigene Zielgruppe;
 *  eine Einreichung wird ein Vorgang, der unter Meldungen erscheint. */
export default async function FormsPage() {
  const t = await getTranslations("Forms");
  const response = await serverFetch("/api/v1/portal/forms");
  redirectIfUnauthenticated(response);
  if (!response.ok) throw new Error(`portal forms ${response.status}`);
  const data = (await response.json()) as PortalForm[];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <p className="text-sm text-muted">{t("intro")}</p>
      <PortalForms forms={data} />
    </div>
  );
}
