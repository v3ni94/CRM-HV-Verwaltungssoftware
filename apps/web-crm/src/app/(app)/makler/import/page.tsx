import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { FlowImport } from "@/components/letting/FlowImport";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

/** FLOW import (M28 stage 4, docs/rules/M28-01.md): upload a FLOW database dump and review
 *  the preview before creating listings. No FLOWFACT call. */
export default async function FlowImportPage() {
  const t = await getTranslations("Broker");
  return (
    <div className="flex flex-col gap-4">
      <Link href="/makler" className="text-sm text-muted hover:underline">
        {t("import.back")}
      </Link>
      <PageHeader title={t("import.title")} />
      <p className="text-sm text-muted">{t("import.intro")}</p>
      <FlowImport />
    </div>
  );
}
