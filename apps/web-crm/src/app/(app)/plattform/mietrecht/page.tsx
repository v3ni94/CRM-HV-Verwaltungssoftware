import { getTranslations } from "next-intl/server";

import { CapAreas, RentLawRules, type CapArea, type RentLawRule } from "@/components/letting/RentLawAdmin";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Rent law rule set (M26-01), maintained by platform administrators. Automatic checks use a
 *  rule only after release; the page itself never opens a gate. */
export default async function RentLawPage() {
  const t = await getTranslations("RentLaw");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  if (!me.data?.is_platform_admin) return <p className={ui.alert}>{t("forbidden")}</p>;
  const [rules, areas] = await Promise.all([
    api.GET("/api/v1/letting/rent-law/rules"),
    api.GET("/api/v1/letting/rent-law/cap-areas"),
  ]);
  return (
    <div className="flex flex-col gap-4">
      <h1 className={ui.title}>{t("title")}</h1>
      <p className={ui.notice}>{t("notice")}</p>
      <section className={ui.card}>
        <h2 className="mb-2 font-medium">{t("rules")}</h2>
        <RentLawRules rules={(rules.data ?? []) as RentLawRule[]} />
      </section>
      <section className={ui.card}>
        <h2 className="mb-2 font-medium">{t("areas")}</h2>
        <CapAreas areas={(areas.data ?? []) as CapArea[]} />
      </section>
    </div>
  );
}
