import { getTranslations } from "next-intl/server";

import { SepaOverview, type SepaMandateRow } from "@/components/contracts/SepaOverview";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";
import { today as businessToday } from "@/lib/today";

export const dynamic = "force-dynamic";

/** SEPA mandates across all contracts (M5-05). */
export default async function SepaOverviewPage() {
  const t = await getTranslations("SepaOverview");
  const tf = await getTranslations("ContractForm");
  const response = await serverFetch("/api/v1/sepa-mandates?limit=1000");
  redirectIfUnauthenticated(response);
  const rows = response.ok ? ((await response.json()) as SepaMandateRow[]) : null;
  const today = businessToday();
  return (
    <div className={ui.pageGap}>
      <PageHeader
        title={t("title")}
        description={t("description")}
        breadcrumb={[{ href: "/vertraege", label: tf("page.list") }, { label: t("title") }]}
      />
      {rows === null ? (
        <p role="alert" className={ui.alert}>
          {t("loadError")}
        </p>
      ) : (
        <SepaOverview rows={rows} today={today} />
      )}
    </div>
  );
}
