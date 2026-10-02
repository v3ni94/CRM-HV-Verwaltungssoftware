import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { AutomationComparison } from "@/components/banking/AutomationComparison";
import { MatchingMetricsCard } from "@/components/banking/MatchingMetricsCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Bank, Automatik-Kennzahlen (7.4, GAH-107, GAH-211): Abdeckung und Fehlerquote der Automatik
 *  sowie Vergleich Automatik gegen manuelle Buchung. Nur Berichte, nichts wird gebucht. */
export default async function AutomationKpiPage() {
  const t = await getTranslations("Bank.kpi");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("description")} />
      <p className="text-sm">
        <Link href="/bank" className="font-medium hover:underline">
          {t("backToBank")}
        </Link>
      </p>
      <MatchingMetricsCard />
      <AutomationComparison />
    </div>
  );
}
