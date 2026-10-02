import { getTranslations } from "next-intl/server";

import { BankLimitsCard } from "@/components/banking/BankLimitsCard";
import { BankStatusImport } from "@/components/banking/BankStatusImport";
import { CreditPayables } from "@/components/banking/CreditPayables";
import { PaymentRunPreview } from "@/components/banking/PaymentRunPreview";
import { PaymentRunSettingsCard } from "@/components/banking/PaymentRunSettingsCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

export default async function PaymentRunPage() {
  const t = await getTranslations("PaymentRun");
  const me = await getMe();
  const canUpdate = (me.data?.permissions ?? []).includes("tenant_settings:update");
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[
          { href: "/bank", label: t("bank") },
          { href: "/bank/zahlungen", label: t("orders") },
        ]}
        title={t("title")}
      />
      <PaymentRunPreview />
      <PaymentRunSettingsCard canUpdate={canUpdate} />
      <CreditPayables />
      <BankStatusImport />
      <BankLimitsCard />
    </div>
  );
}
