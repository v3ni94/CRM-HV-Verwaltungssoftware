import { getTranslations } from "next-intl/server";

import { ReceivableRunPanel } from "@/components/accounting/ReceivableRunPanel";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

export default async function ReceivablesPage() {
  const t = await getTranslations("Receivables");
  const month = new Date().toISOString().slice(0, 7);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <ReceivableRunPanel initialMonth={month} />
    </div>
  );
}
