import { getTranslations } from "next-intl/server";

import { DataChangeForm } from "@/components/portal/DataChangeForm";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function DataChangePage() {
  const t = await getTranslations("DataChange");
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <DataChangeForm />
    </div>
  );
}
