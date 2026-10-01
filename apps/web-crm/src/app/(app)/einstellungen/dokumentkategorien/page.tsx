import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { CategoryTree, type TreeCategory } from "@/components/documents/CategoryTree";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Einstellungen, Dokumentkategorien (6.7, M6-09): Kategoriebaum mit Zuordnung zu
 *  Paperless-Dokumenttyp, Paperless-Tag und Drive-Ordner. */
export default async function DocumentCategoriesPage() {
  const t = await getTranslations("CategoryTree");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("tenant_settings:update")) notFound();
  const res = await serverFetch("/api/v1/document-categories");
  const categories = res.ok ? ((await res.json()) as TreeCategory[]) : [];
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/einstellungen", label: t("breadcrumb") }]} title={t("title")} description={t("intro")} />
      <CategoryTree categories={categories} />
    </div>
  );
}
