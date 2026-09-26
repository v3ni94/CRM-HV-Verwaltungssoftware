import { getTranslations } from "next-intl/server";

import { StartTiles } from "@/components/portal/StartTiles";
import type { Me } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Start page after login: role aware. Providers see their orders only; tenants and owners
 *  see documents, tickets, account statement, meter reading and data change. */
export default async function StartPage() {
  const t = await getTranslations("Portal");
  const { data, error, response } = await serverApi().GET("/api/v1/portal/me");
  redirectIfUnauthenticated(response);
  if (!data) throw new Error(String(error));
  const me = data as unknown as Me;
  // Hint on new notices of the Schwarzes Brett (A54); any failure hides the hint only.
  let newNotices = 0;
  if (!me.roles.includes("provider")) {
    const notices = await serverFetch("/api/v1/portal/notices");
    if (notices.ok) newNotices = ((await notices.json()) as { is_new: boolean }[]).filter((n) => n.is_new).length;
  }
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("start.title")}</h1>
      <StartTiles me={me} newNotices={newNotices} />
    </div>
  );
}
