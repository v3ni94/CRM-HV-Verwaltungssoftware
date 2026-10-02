import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { CreditorIdsOverview, type CreditorIdRow } from "@/components/banking/CreditorIdsOverview";
import { BankConnectionsPanel } from "@/components/banking/BankConnectionsPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Bankverbindungen (AF03, GAF-03): Verbindungen, Sync-Protokoll, Entscheidungsprotokoll.
 *  Lesen mit accounting:read, Anlegen und Schalter mit accounting:approve. */
export default async function BankConnectionsPage() {
  const t = await getTranslations("BankConnections");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("accounting:read")) notFound();
  const idsRes = await serverFetch("/api/v1/accounting/direct-debits/creditor-ids");
  const ids: CreditorIdRow[] = idsRes.ok ? ((await idsRes.json()) as CreditorIdRow[] | null) ?? [] : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/bank", label: t("bank") }]} title={t("title")} description={t("intro")} />
      <CreditorIdsOverview rows={ids} />
      <BankConnectionsPanel canApprove={permissions.includes("accounting:approve")} />
    </div>
  );
}
