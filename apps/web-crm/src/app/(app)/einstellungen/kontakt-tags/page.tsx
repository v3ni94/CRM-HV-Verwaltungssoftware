import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { ContactTagsAdmin } from "@/components/settings/ContactTagsAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Tag-Verwaltung der Kontakte (M3-04): Anzeige mit contacts:read, Ändern mit contacts:update,
 *  Löschen mit contacts:delete (vom Backend geprüft; hier nur die Anzeige der Aktionen). */
export default async function ContactTagsPage() {
  const t = await getTranslations("ContactTagsAdmin");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("contacts:read")) notFound();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[{ href: "/einstellungen", label: t("breadcrumb") }, { label: t("title") }]}
        title={t("title")}
      />
      <ContactTagsAdmin canUpdate={permissions.includes("contacts:update")} canDelete={permissions.includes("contacts:delete")} />
    </div>
  );
}
