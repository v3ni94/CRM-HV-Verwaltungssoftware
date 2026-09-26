import { getTranslations } from "next-intl/server";

import { ContractApprovalPanel, type PendingContract } from "@/components/contracts/ContractApprovalPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Freigabe der Importverträge vor der ersten Sollstellung (Betreiberauftrag 26.09.2026). */
export default async function ContractApprovalPage() {
  const t = await getTranslations("ContractApproval");
  const tf = await getTranslations("ContractForm");
  const [me, response] = await Promise.all([getMe(), serverFetch("/api/v1/contracts/pending-approval?limit=5000")]);
  redirectIfUnauthenticated(response);
  const rows = response.ok ? ((await response.json()) as PendingContract[]) : null;
  const canApprove = (me.data?.permissions ?? []).includes("contracts:approve");
  return (
    <div className={ui.pageGap}>
      <PageHeader
        title={t("title")}
        description={t("description")}
        breadcrumb={[{ href: "/vertraege", label: tf("page.list") }, { label: t("title") }]}
      />
      {rows === null ? (
        <p role="alert" className={ui.alert}>
          {t("loadError")}
        </p>
      ) : (
        <ContractApprovalPanel initial={rows} canApprove={canApprove} />
      )}
    </div>
  );
}
