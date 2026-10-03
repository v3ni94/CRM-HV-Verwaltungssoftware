import { getTranslations } from "next-intl/server";

import { DepositList, type DepositRow } from "@/components/letting/DepositList";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { fetchAllListPages } from "@/lib/list-all";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Kautionsliste je Mietverhältnis (GAM-211): GET /deposits seitenweise, Detail je Kaution im Client. */
export default async function DepositsPage() {
  const [t, tl] = await Promise.all([getTranslations("DepositList"), getTranslations("Letting")]);
  const { response, items } = await fetchAllListPages<DepositRow>("/api/v1/deposits");
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} breadcrumb={[{ href: "/vermietung", label: tl("title") }]} />
      {items === null ? <p role="alert" className={ui.alert}>{t("detail.loadError")}</p> : <DepositList rows={items} />}
    </div>
  );
}
