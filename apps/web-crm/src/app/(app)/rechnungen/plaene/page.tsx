import { getTranslations } from "next-intl/server";

import { RecurringPlansPanel } from "@/components/invoices/RecurringPlansPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";

export const dynamic = "force-dynamic";

export default async function Page() {
  const t = await getTranslations("RecurringPlans");
  const ledgers = await serverApi().GET("/api/v1/accounting/ledgers");
  redirectIfUnauthenticated(ledgers.response);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <RecurringPlansPanel ledgers={(ledgers.data ?? []).map((l) => ({ id: l.id, label: l.name }))} />
    </div>
  );
}
