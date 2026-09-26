import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { ui } from "@/lib/ui";

/** 404 of the signed-in area (unknown ticket, order or engagement): German notice with a way
 *  back instead of the framework default. */
export default async function PortalNotFound() {
  const t = await getTranslations("Portal");
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("notFoundTitle")}</h1>
      <p className="text-sm text-muted">{t("notFoundHint")}</p>
      <Link href="/start" className={`${ui.secondary} ${ui.actionFull}`}>
        {t("toStart")}
      </Link>
    </div>
  );
}
