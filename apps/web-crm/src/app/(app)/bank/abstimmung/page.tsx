import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { BankReconciliation } from "@/components/banking/BankReconciliation";
import { ReconciliationSettingsPanel } from "@/components/banking/ReconciliationSettingsPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Bank reconciliation B09: statement balances against movements and the ledger, read only. */
export default async function BankReconciliationPage() {
  const t = await getTranslations("Bank.reconciliation");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("description")} />
      <p className="text-sm">
        <Link href="/bank" className="font-medium hover:underline">
          {t("backToBank")}
        </Link>
      </p>
      <BankReconciliation />
      <ReconciliationSettingsPanel />
    </div>
  );
}
