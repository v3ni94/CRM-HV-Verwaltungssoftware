import { getTranslations } from "next-intl/server";

import { ResolutionList } from "@/components/portal/ResolutionList";
import type { PortalResolution } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Beschluss-Sammlung (A51, Rolle Eigentümer): nur verkündete Beschlüsse der eigenen
 *  Gemeinschaft, lesend. Mieter und Dienstleister erhalten von der API 403 und sehen einen
 *  Hinweis statt der Liste. */
export default async function ResolutionsPage() {
  const t = await getTranslations("Resolutions");
  const response = await serverFetch("/api/v1/portal/resolutions");
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
  const rows = (await response.json()) as PortalResolution[];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <p className="text-sm text-muted">{t("intro")}</p>
      <ResolutionList rows={rows} />
    </div>
  );
}
