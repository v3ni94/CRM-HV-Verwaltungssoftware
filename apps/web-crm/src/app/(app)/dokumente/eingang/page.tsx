import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { IntakeProposals } from "@/components/documents/IntakeProposals";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Eingangsvorschläge des Dokumenteingangs (Abschnitt 8, 11.4, GAF-01). */
export default async function IntakeProposalsPage() {
  const t = await getTranslations("IntakeProposals");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("documents:read")) notFound();
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/dokumente", label: t("breadcrumb") }]} title={t("title")} description={t("intro")} />
      <IntakeProposals canUpdate={permissions.includes("documents:update")} />
    </div>
  );
}
