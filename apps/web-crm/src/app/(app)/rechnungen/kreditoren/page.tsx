import { getTranslations } from "next-intl/server";

import { CreditorsPanel } from "@/components/invoices/CreditorsPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function Page() {
  const t = await getTranslations("Creditors");
  const ledgers = await serverApi().GET("/api/v1/accounting/ledgers");
  redirectIfUnauthenticated(ledgers.response);
  if (!ledgers.response.ok) return <p role="alert" className={ui.alert}>{t("loadError")}</p>;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <CreditorsPanel ledgers={(ledgers.data ?? []).map((l) => ({ id: l.id, label: l.name }))} />
    </div>
  );
}
