import { getTranslations } from "next-intl/server";

import { SepaOverview, type SepaMandateRow } from "@/components/contracts/SepaOverview";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { fetchAllListPages } from "@/lib/list-all";
import { ui } from "@/lib/ui";
import { today as businessToday } from "@/lib/today";

export const dynamic = "force-dynamic";

/** SEPA mandates across all contracts (M5-05). */
export default async function SepaOverviewPage() {
  const t = await getTranslations("SepaOverview");
  const tf = await getTranslations("ContractForm");
  const { response, items: rows } = await fetchAllListPages<SepaMandateRow>("/api/v1/sepa-mandates");
  redirectIfUnauthenticated(response);
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
