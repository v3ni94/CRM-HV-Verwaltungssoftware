import { getTranslations } from "next-intl/server";

import { CircularVotePanel } from "@/components/portal/CircularVotePanel";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Umlaufbeschlüsse der eigenen Gemeinschaft (AG07 / GAF-32, Rolle Eigentümer). */
export default async function CircularResolutionsPage() {
  const t = await getTranslations("PortalCircular");
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <p className="text-sm text-muted">{t("intro")}</p>
      <CircularVotePanel />
    </div>
  );
}
