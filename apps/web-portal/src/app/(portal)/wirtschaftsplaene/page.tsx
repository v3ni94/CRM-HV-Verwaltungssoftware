import { getTranslations } from "next-intl/server";

import { OwnerPlanList, type OwnerPlan } from "@/components/portal/OwnerReports";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Beschlossene Wirtschaftspläne der eigenen Gemeinschaft (GAF-33), lesend, hinter G4. */
export default async function OwnerPlansPage() {
  const t = await getTranslations("OwnerPlans");
  const response = await serverFetch("/api/v1/portal/owner/plans");
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
  const { items, texts, note } = (await response.json()) as { items: OwnerPlan[]; texts: Record<string, string>; note: string };
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      {note ? <p className="text-xs text-subtle">{note}</p> : null}
      <OwnerPlanList items={items} texts={texts} />
    </div>
  );
}
