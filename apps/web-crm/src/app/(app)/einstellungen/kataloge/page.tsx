import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import {
  CatalogAdmin,
  type CatalogSummary,
} from "@/components/settings/CatalogAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Einstellungen, Kataloge (P1 AP4, 4.11 und Anhang B): alle Auswahllisten je Mandant.
 *  Lesen mit properties:read, Pflege mit tenant_settings:update. */
export default async function CatalogsSettingsPage() {
  const t = await getTranslations("Settings.catalogs");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("properties:read")) notFound();
  const res = await serverFetch("/api/v1/catalogs");
  const catalogs = res.ok ? ((await res.json()) as CatalogSummary[]) : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      <CatalogAdmin
        catalogs={catalogs}
        canManage={permissions.includes("tenant_settings:update")}
      />
    </div>
  );
}
