import { getTranslations } from "next-intl/server";

import { NoticeList, type PortalNotice } from "@/components/portal/NoticeList";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Schwarzes Brett (M21-01, A54): notices of the own properties, current on the day and for
 *  the own role. Read server side; attachments go through /api/portal-files. */
export default async function NoticesPage() {
  const t = await getTranslations("Notices");
  const response = await serverFetch("/api/v1/portal/notices");
  redirectIfUnauthenticated(response);
  if (!response.ok) throw new Error(String(response.status));
  const notices = (await response.json()) as PortalNotice[];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <p className="text-sm text-muted">{t("intro")}</p>
      <NoticeList notices={notices} />
    </div>
  );
}
