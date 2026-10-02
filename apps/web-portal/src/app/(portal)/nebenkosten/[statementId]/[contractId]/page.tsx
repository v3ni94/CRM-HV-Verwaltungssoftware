import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { TenantStatementDetail, type TenantStatementDetailData } from "@/components/portal/TenantStatements";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

const ID = /^[0-9a-fA-F-]{36}$/;

/** GAC-02: Abrechnung eines eigenen Mietvertrags; der Abruf wird als Indiz vermerkt. */
export default async function TenantStatementPage({
  params,
}: {
  params: Promise<{ statementId: string; contractId: string }>;
}) {
  const { statementId, contractId } = await params;
  if (!ID.test(statementId) || !ID.test(contractId)) notFound();
  const t = await getTranslations("TenantStatements");
  const response = await serverFetch(`/api/v1/portal/tenant-statements/${statementId}/contracts/${contractId}`);
  redirectIfUnauthenticated(response);
  if (response.status === 404) notFound();
  if (response.status === 403) {
    return (
      <div className={ui.pageGap}>
        <h1 className={ui.title}>{t("title")}</h1>
        <p className={ui.notice}>{t("locked")}</p>
      </div>
    );
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = (await response.json()) as TenantStatementDetailData;
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <TenantStatementDetail data={data} />
    </div>
  );
}
