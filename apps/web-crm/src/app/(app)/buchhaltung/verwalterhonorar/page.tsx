import { getTranslations } from "next-intl/server";

import { AdminFeePanel, type PropertyOption } from "@/components/accounting/AdminFeePanel";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";
import { today } from "@/lib/today";

export const dynamic = "force-dynamic";

export default async function AdminFeesPage() {
  const t = await getTranslations("AdminFees");
  const { data, response } = await serverApi().GET("/api/v1/properties", { params: { query: { page_size: 200 } } });
  redirectIfUnauthenticated(response);
  if (!response.ok) return <p role="alert" className={ui.alert}>{t("loadError")}</p>;
  const rows = (Array.isArray(data) ? data : []) as { id: string; number: string; name: string }[];
  const properties: PropertyOption[] = rows.map((p) => ({ id: p.id, label: `${p.number} ${p.name}` }));
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <AdminFeePanel properties={properties} today={today()} />
    </div>
  );
}
