import { getTranslations } from "next-intl/server";

import { PortalAssistant } from "@/components/portal/PortalAssistant";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Assistent für die eigenen Unterlagen (AE28, M7-06, SA-04). Die Seite ist nur verlinkt, wenn
 *  der Mandant den Chat-Bot eingeschaltet hat; die Komponente fragt den Stand bei der API ab und
 *  zeigt bei gesperrtem Schalter einen Hinweis. Die Rechte prüft allein die API. */
export default async function AssistantPage() {
  const t = await getTranslations("Assistant");
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <p className="text-sm text-muted">{t("intro")}</p>
      <PortalAssistant />
    </div>
  );
}
