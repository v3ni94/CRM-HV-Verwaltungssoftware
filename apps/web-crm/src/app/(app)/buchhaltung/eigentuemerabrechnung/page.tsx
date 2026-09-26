import { getTranslations } from "next-intl/server";

import { OwnerStatementPanel } from "@/components/billing/OwnerStatementPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function OwnerStatementsPage() {
  const t = await getTranslations("OwnerStatements");
  const { data, error, response } = await serverApi().GET("/api/v1/accounting/ledgers");
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/buchhaltung", label: t("accounting") }]} title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.length === 0 ? (
        <p className={ui.help}>{t("noLedgers")}</p>
      ) : null}
      <OwnerStatementPanel ledgers={(data ?? []).map((l) => ({ id: l.id, name: l.name }))} />
    </div>
  );
}
