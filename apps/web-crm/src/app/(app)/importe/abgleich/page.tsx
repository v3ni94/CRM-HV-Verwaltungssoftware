import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { ReconciliationReports } from "@/components/imports/ReconciliationReports";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Abgleichberichte des Parallelbetriebs (13.1, A68): nur lesen und vergleichen. */
export default async function ReconciliationPage() {
  const t = await getTranslations("ReconciliationReports");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const canCreate = me.data?.permissions.includes("ai:create") ?? false;
  return (
    <div className="flex flex-col gap-4">
      <Link href="/importe" className="text-sm text-muted hover:underline">
        {t("backToImports")}
      </Link>
      <PageHeader title={t("title")} description={t("intro")} />
      <ReconciliationReports canCreate={canCreate} />
    </div>
  );
}
