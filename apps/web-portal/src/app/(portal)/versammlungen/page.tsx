import { getTranslations } from "next-intl/server";

import { MeetingList } from "@/components/portal/MeetingList";
import type { PortalMeeting } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Eigentümerversammlungen der eigenen Gemeinschaft (M25-03, V13, Rolle Eigentümer): Termin,
 *  Form und, nur bei hybrider oder virtueller Form nach Einladung, die Einwahldaten. Mieter
 *  und Dienstleister erhalten von der API 403 und sehen einen Hinweis. */
export default async function MeetingsPage() {
  const t = await getTranslations("Meetings");
  const response = await serverFetch("/api/v1/portal/meetings");
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
  const rows = (await response.json()) as PortalMeeting[];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <p className="text-sm text-muted">{t("intro")}</p>
      <MeetingList rows={rows} />
    </div>
  );
}
