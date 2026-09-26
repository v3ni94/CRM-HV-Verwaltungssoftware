import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { TicketTemplatesAdmin, type TicketTemplate } from "@/components/settings/TicketTemplatesAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Ticketvorlagen mit Checkliste und Zusatzfeldern (M19-02): Lesen mit tickets:read,
 *  Anlegen/Bearbeiten mit tickets:approve oder tenant_settings:update (vom Backend geprüft;
 *  hier nur die Anzeige der Aktionen). */
export default async function TicketTemplatesPage() {
  const t = await getTranslations("TicketTemplates");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tickets:read")) notFound();
  const canManage = permissions.includes("tickets:approve") || permissions.includes("tenant_settings:update");
  const res = await serverFetch("/api/v1/tickets/templates");
  const templates = res.ok ? ((await res.json()) as TicketTemplate[]) : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("description")} />
      <TicketTemplatesAdmin initialTemplates={templates} canManage={canManage} />
    </div>
  );
}
