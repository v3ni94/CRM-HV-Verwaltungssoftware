import { getTranslations } from "next-intl/server";

import { BankStatusImport } from "@/components/banking/BankStatusImport";
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
      <BankStatusImport />
    </div>
  );
}
