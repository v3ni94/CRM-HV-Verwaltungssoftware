import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import {
  WebhookSubscriptionsAdmin,
  type WebhookEventType,
  type WebhookSubscription,
} from "@/components/settings/WebhookSubscriptionsAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Ausgehende Webhook-Abonnements (Abschnitt 12, A69, Lückenliste A89): Liste, Anlegen,
 *  Deaktivieren, Löschen und Zustellprotokoll. Die Seite verlangt tenant_settings:update; die
 *  Schnittstelle prüft zusätzlich die Rechte webhooks:read/create/update/delete. */
export default async function WebhookSettingsPage() {
  const t = await getTranslations("Webhooks");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tenant_settings:update")) notFound();
  const [hooksRes, typesRes] = await Promise.all([
    serverFetch("/api/v1/tenant/webhooks"),
    serverFetch("/api/v1/tenant/webhooks/event-types"),
  ]);
  const initial: WebhookSubscription[] = hooksRes.ok ? ((await hooksRes.json()) as WebhookSubscription[]) : [];
  const eventTypes: WebhookEventType[] = typesRes.ok ? ((await typesRes.json()) as WebhookEventType[]) : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("pageIntro")} />
      <WebhookSubscriptionsAdmin
        initial={initial}
        eventTypes={eventTypes}
        loadFailed={!hooksRes.ok}
        canManage={permissions.includes("webhooks:create") || permissions.includes("webhooks:update")}
        canDelete={permissions.includes("webhooks:delete")}
      />
    </div>
  );
}
