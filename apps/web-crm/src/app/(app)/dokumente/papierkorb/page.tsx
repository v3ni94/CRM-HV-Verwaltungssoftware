import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { DocumentTrash, type TrashEntry } from "@/components/documents/DocumentTrash";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Papierkorb (AE33, AC07-03): gelöschte Dokumente bis zur endgültigen Löschung. Nur mit dem
 *  Recht zum Löschen sichtbar; Wiederherstellung und vorzeitige Löschung sind protokolliert. */
export default async function DocumentTrashPage() {
  const t = await getTranslations("DocumentTrash");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("documents:delete")) notFound();
  const res = await serverFetch("/api/v1/documents/trash");
  const entries = res.ok ? ((await res.json()) as TrashEntry[]) : [];
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/dokumente", label: t("breadcrumb") }]} title={t("title")} description={t("intro")} />
      <DocumentTrash entries={entries} canDelete={true} />
    </div>
  );
}
