import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { BankAccountOverview } from "@/components/banking/BankAccountOverview";
import { BankSetupWizard } from "@/components/banking/BankSetupWizard";
import { FinApiConnections } from "@/components/banking/FinApiConnections";
import { FinTsConnections } from "@/components/banking/FinTsConnections";
import { MatchingMetricsCard } from "@/components/banking/MatchingMetricsCard";
import { StatementImport } from "@/components/banking/StatementImport";
import { TransactionList } from "@/components/banking/TransactionList";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Bank (M11, M12, BK-2): statement upload, account overview, connections and the daily work
 *  list with booking dialog, duplicate clarification and bulk confirmation. Authorization stays
 *  with the API; the buttons follow the viewer's permissions. */
export default async function BankPage() {
  const t = await getTranslations("Bank");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <nav aria-label={t("subpages")} className="flex flex-wrap gap-x-4 gap-y-1 text-sm font-medium">
        <Link href="/bank/zahlungen" className="hover:underline">
          {t("ordersLink")}
        </Link>
        <Link href="/bank/lastschriften" className="hover:underline">
          {t("directDebitsLink")}
        </Link>
        <Link href="/bank/regeln" className="hover:underline">
          {t("rulesLink")}
        </Link>
        <Link href="/bank/abstimmung" className="hover:underline">
          {t("reconciliationLink")}
        </Link>
        <Link href="/bank/nachkontrolle" className="hover:underline">
          {t("reviewLink")}
        </Link>
        <Link href="/einstellungen/buchhaltung/automatik" className="hover:underline">
          {t("levelsLink")}
        </Link>
      </nav>
      <BankSetupWizard />
      <BankAccountOverview />
      <FinTsConnections />
      <FinApiConnections />
      <StatementImport />
      <MatchingMetricsCard />
      <TransactionList canBook={permissions.includes("accounting:create")} canUpdate={permissions.includes("accounting:update")} />
    </div>
  );
}
