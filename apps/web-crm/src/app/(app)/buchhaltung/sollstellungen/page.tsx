import { getTranslations } from "next-intl/server";

import { ReceivableRunPanel } from "@/components/accounting/ReceivableRunPanel";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

export default async function ReceivablesPage() {
  const t = await getTranslations("Receivables");
  const me = await getMe();
  const month = new Date().toISOString().slice(0, 7);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <ReceivableRunPanel initialMonth={month} canApprove={me.data?.permissions.includes("accounting:approve") ?? false} />
    </div>
  );
}
