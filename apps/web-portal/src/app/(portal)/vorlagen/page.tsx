import { getTranslations } from "next-intl/server";

import { BoardSubmissions } from "@/components/portal/BoardSubmissions";
import type { PortalBoardSubmission } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Vorlagen der Verwaltung an den Verwaltungsbeirat (M19-02): Kenntnisnahme oder Votum bis
 *  zur Frist. Nur Beiratsmitglieder der eigenen GdWE sehen Vorlagen; das Votum ist eine
 *  Information, Beauftragung und Zahlung bleiben bei der Verwaltung. */
export default async function BoardSubmissionsPage() {
  const t = await getTranslations("BoardSubmissions");
  const response = await serverFetch("/api/v1/portal/board/submissions");
  redirectIfUnauthenticated(response);
  const rows = response.ok ? ((await response.json()) as PortalBoardSubmission[]) : [];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <p className={ui.notice}>{t("roleNotice")}</p>
      <BoardSubmissions initial={rows} />
    </div>
  );
}
