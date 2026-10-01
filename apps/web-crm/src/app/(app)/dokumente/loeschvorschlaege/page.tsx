import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DeletionProposals, type DeletionProposal } from "@/components/documents/DeletionProposals";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Löschvorschläge (M6-04, 6.9.5): Liste der monatlichen und manuellen Läufe, Freigabe im
 *  Vier-Augen-Prinzip, Ausführung durch eine dritte Person, Löschprotokoll je Dokument. */
export default async function DeletionProposalsPage() {
  const t = await getTranslations("DeletionProposals");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("documents:read")) notFound();
  const res = await serverFetch("/api/v1/deletion-proposals");
  const proposals = res.ok ? ((await res.json()) as DeletionProposal[]) : [];
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/dokumente", label: t("breadcrumb") }]} title={t("title")} description={t("intro")} />
      {permissions.includes("documents:delete") ? (
        <p className="text-sm">
          <Link href="/dokumente/papierkorb" className="underline">
            {t("trashLink")}
          </Link>
        </p>
      ) : null}
      <DeletionProposals
        proposals={proposals}
        userId={me.data?.user_id ?? null}
        canApprove={permissions.includes("documents:approve")}
        canDelete={permissions.includes("documents:delete")}
      />
    </div>
  );
}
