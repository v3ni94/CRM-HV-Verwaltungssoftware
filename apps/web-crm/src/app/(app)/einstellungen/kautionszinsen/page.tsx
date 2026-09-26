import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { DepositInterestRatesAdmin, type ReferenceRate } from "@/components/settings/DepositInterestRatesAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Einstellungen, Kautionszinsen (M5-02): Referenzzinssatz je Jahr. Lesen mit contracts:read,
 *  Pflege mit tenant_settings:update. */
export default async function DepositInterestRatesPage() {
  const t = await getTranslations("DepositInterestRates");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("contracts:read")) notFound();
  const res = await serverFetch("/api/v1/deposit-interest-rates");
  const rates = res.ok ? ((await res.json()) as ReferenceRate[]) : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} breadcrumb={[{ href: "/einstellungen", label: t("settings") }]} />
      <DepositInterestRatesAdmin rates={rates} canManage={permissions.includes("tenant_settings:update")} />
    </div>
  );
}
