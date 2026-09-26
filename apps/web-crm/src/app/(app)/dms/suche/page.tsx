import { getTranslations } from "next-intl/server";

import { DmsSearch } from "@/components/dms/DmsSearch";
import { DmsUpload } from "@/components/dms/DmsUpload";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

/** Document search over Paperless and upload with the object it belongs to (26.09.2026). Daily
 *  work with the archive happens here; the Paperless web interface stays for administration. */
export default async function DmsSearchPage() {
  const t = await getTranslations("DmsSearch");
  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow={t("area")} title={t("pageTitle")} description={t("intro")} breadcrumb={[{ href: "/dms", label: t("area") }, { label: t("pageTitle") }]} />
      <DmsUpload />
      <DmsSearch />
    </div>
  );
}
