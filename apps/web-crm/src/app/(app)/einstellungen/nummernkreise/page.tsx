import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { TenantDefaultsAdmin, type NumberFormatEntry } from "@/components/settings/TenantDefaultsAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** GA01-07 und GA01-08: Standard-Zustellweg und Nummernkreise des Mandanten. */
export default async function NumberCirclesPage() {
  const t = await getTranslations("AA17");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("tenant_settings:update")) notFound();
  const [channel, formats] = await Promise.all([
    serverFetch("/api/v1/tenant/delivery-default"),
    serverFetch("/api/v1/tenant/number-formats"),
  ]);
  const channelData = channel.ok ? ((await channel.json()) as { default_delivery_channel: "post" | "email" | "portal" }) : null;
  const formatData = formats.ok ? ((await formats.json()) as { formats: NumberFormatEntry[] }) : { formats: [] };
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("cardTitle")} description={t("cardDescription")} />
      <TenantDefaultsAdmin initialChannel={channelData?.default_delivery_channel ?? "post"} initialFormats={formatData.formats} />
    </div>
  );
}
