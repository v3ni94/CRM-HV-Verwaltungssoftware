import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { ui } from "@/lib/ui";

export const dynamic = "force-static";

/** Erklärung zur Barrierefreiheit (V13, BFSG als Einschätzung): öffentlich ohne Anmeldung
 *  erreichbar, damit sie unabhängig vom Portalzugang aufgerufen werden kann. Pflichtinhalte als
 *  Entwurf; noch offene Angaben sind als [zu ergänzen] markiert (docs/OPEN_QUESTIONS.md). */
export default async function AccessibilityPage() {
  const t = await getTranslations("Accessibility");
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-8">
      <h1 className={ui.title}>{t("title")}</h1>
      <p className="text-sm text-muted">{t("intro")}</p>
      <section className="flex flex-col gap-1">
        <h2 className={ui.h2}>{t("statusTitle")}</h2>
        <p className="text-sm text-muted">{t("status")}</p>
      </section>
      <section className="flex flex-col gap-1">
        <h2 className={ui.h2}>{t("scopeTitle")}</h2>
        <p className="text-sm text-muted">{t("scope")}</p>
      </section>
      <section className="flex flex-col gap-1">
        <h2 className={ui.h2}>{t("preparationTitle")}</h2>
        <p className="text-sm text-muted">{t("preparation")}</p>
      </section>
      <section className="flex flex-col gap-1">
        <h2 className={ui.h2}>{t("contactTitle")}</h2>
        <p className="text-sm text-muted">{t("contact")}</p>
      </section>
      <section className="flex flex-col gap-1">
        <h2 className={ui.h2}>{t("enforcementTitle")}</h2>
        <p className="text-sm text-muted">{t("enforcement")}</p>
      </section>
      <Link href="/start" className={`${ui.secondary} ${ui.actionFull} w-fit`}>
        {t("backToStart")}
      </Link>
    </div>
  );
}
