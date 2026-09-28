import { getTranslations } from "next-intl/server";

import { DmsFolderStructure } from "@/components/dms/DmsFolderStructure";
import { DmsSearch } from "@/components/dms/DmsSearch";
import { DmsUpload } from "@/components/dms/DmsUpload";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Document search over Paperless and upload with the object it belongs to (26.09.2026),
 *  category, contract and contact (Package F). Daily work with the archive happens here; the
 *  Paperless web interface stays for administration. The folder structure of the property
 *  file (11.2) is described below the upload. */
export default async function DmsSearchPage() {
  const t = await getTranslations("DmsSearch");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const canEnsureDefaults = me.data?.permissions.includes("tenant_settings:update") ?? false;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow={t("area")} title={t("pageTitle")} description={t("intro")} breadcrumb={[{ href: "/dms", label: t("area") }, { label: t("pageTitle") }]} />
      <DmsUpload />
      <DmsFolderStructure canEnsureDefaults={canEnsureDefaults} />
      <DmsSearch />
    </div>
  );
}
