import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { ContactMergeAdmin } from "@/components/contacts/ContactMergeAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Kontakt-Zusammenführung (M3-03): Vorschlag mit contacts:update, Ausführung und Ablehnung
 *  mit contacts:approve durch eine zweite Person (vom Backend geprüft). */
export default async function ContactMergePage() {
  const t = await getTranslations("ContactMerge");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("contacts:read")) notFound();
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/kontakte", label: t("breadcrumb") }]} title={t("title")} description={t("intro")} />
      <ContactMergeAdmin canPropose={permissions.includes("contacts:update")} canApprove={permissions.includes("contacts:approve")} />
    </div>
  );
}
