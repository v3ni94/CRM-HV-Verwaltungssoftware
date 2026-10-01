import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { PortalProviderAdmin, type EntityOption } from "@/components/settings/PortalProviderAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Dienstleister im Portal (GA11-04, AB12): Verfügbarkeitsfenster und Klassenfreigaben. Lesen und
 *  Pflegen verlangt contacts:update (vom Backend geprüft); Bewertungen werden nicht angezeigt. */
export default async function PortalProvidersPage() {
  const t = await getTranslations("PortalProviders");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("contacts:update")) notFound();
  const [entitiesRes, profilesRes] = await Promise.all([
    serverFetch("/api/v1/tenant/legal-entities"),
    serverFetch("/api/v1/retention-profiles"),
  ]);
  const legalEntities = entitiesRes.ok ? ((await entitiesRes.json()) as EntityOption[]) : [];
  const profiles = profilesRes.ok ? ((await profilesRes.json()) as { document_class: string }[]) : [];
  const documentClasses = [...new Set(profiles.map((p) => p.document_class))].sort();
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader
        breadcrumb={[{ href: "/einstellungen", label: t("breadcrumb") }]}
        title={t("title")}
        description={t("description")}
      />
      <PortalProviderAdmin canManage legalEntities={legalEntities} documentClasses={documentClasses} />
    </div>
  );
}
