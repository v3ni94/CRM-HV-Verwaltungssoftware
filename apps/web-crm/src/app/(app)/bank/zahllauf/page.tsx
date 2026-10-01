import { getTranslations } from "next-intl/server";

import { BankLimitsCard } from "@/components/banking/BankLimitsCard";
import { BankStatusImport } from "@/components/banking/BankStatusImport";
import { CreditPayables } from "@/components/banking/CreditPayables";
import { PaymentRunPreview } from "@/components/banking/PaymentRunPreview";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

export default async function PaymentRunPage() {
  const t = await getTranslations("PaymentRun");
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
      <CreditPayables />
      <BankStatusImport />
      <BankLimitsCard />
    </div>
  );
}
