import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { CreditorIdsCard, type CreditorEntity } from "@/components/banking/CreditorIdsCard";
import { CreditorIdsOverview, type CreditorIdRow } from "@/components/banking/CreditorIdsOverview";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Einstellungen, Buchhaltung, Gläubiger-ID (AF03, GAF-04): je Rechtsträger, Rückfall Mandant. */
export default async function CreditorIdsPage() {
  const t = await getTranslations("CreditorIds");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("accounting:read")) notFound();
  const res = await serverFetch("/api/v1/tenant/legal-entities");
  const entities: CreditorEntity[] = res.ok ? ((await res.json()) as CreditorEntity[] | null) ?? [] : [];
  const idsRes = await serverFetch("/api/v1/accounting/direct-debits/creditor-ids");
  const ids: CreditorIdRow[] = idsRes.ok ? ((await idsRes.json()) as CreditorIdRow[] | null) ?? [] : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      <CreditorIdsOverview rows={ids} />
      <CreditorIdsCard
        entities={entities.map((e) => ({ id: e.id, name: e.name }))}
        canUpdate={permissions.includes("accounting:update")}
        canUpdateTenant={permissions.includes("tenant_settings:update")}
      />
    </div>
  );
}
