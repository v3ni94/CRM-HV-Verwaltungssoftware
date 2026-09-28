import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { AutomationSwitchCard } from "@/components/banking/AutomationSwitchCard";
import { BankRules } from "@/components/banking/BankRules";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Bank rules (6.9.4, 7.4 Nr. 4, D51): propose, approve by a second person, activate with an
 *  amount cap and test evidence, disable; plus the read only tenant automation switch. */
export default async function BankRulesPage() {
  const t = await getTranslations("Bank.rules");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("description")} />
      <p className="text-sm">
        <Link href="/bank" className="font-medium hover:underline">
          {t("backToBank")}
        </Link>
      </p>
      <AutomationSwitchCard />
      <BankRules
        canCreate={permissions.includes("accounting:create")}
        canApprove={permissions.includes("accounting:approve")}
        canUpdate={permissions.includes("accounting:update")}
        userId={me.data?.user_id ?? null}
      />
    </div>
  );
}
