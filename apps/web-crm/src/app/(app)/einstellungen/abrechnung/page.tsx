import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { CostTypeAccountsAdmin } from "@/components/settings/CostTypeAccountsAdmin";
import { HeatingRuleTablesAdmin } from "@/components/settings/HeatingRuleTablesAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Einstellungen, Abrechnung (GAF-12): Heizkosten-Regeltabellen und Kostenart-Konto-Zuordnung.
 *  Lesen mit accounting:read, Pflege mit accounting:approve (Tabellen) und accounting:update (Zuordnung). */
export default async function BillingSetupPage() {
  const t = await getTranslations("BillingSetup");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("accounting:read")) notFound();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("title")} description={t("intro")} breadcrumb={[{ href: "/einstellungen", label: t("settings") }]} />
      <HeatingRuleTablesAdmin canManage={permissions.includes("accounting:approve")} />
      <CostTypeAccountsAdmin canManage={permissions.includes("accounting:update")} />
    </div>
  );
}
