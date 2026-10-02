import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { ObjektakteImportRun } from "@/components/imports/ObjektakteImportRun";
import { PreviewImportRun } from "@/components/imports/PreviewImportRun";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Übernahme aus objektakte (M35): Importlauf mit Vorschau, OCR-Cache, Vorschaubild-Übernahme. */
export default async function ObjektakteImportPage() {
  const t = await getTranslations("ObjektakteImportRun");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  return (
    <div className="flex flex-col gap-4">
      <Link href="/importe" className="text-sm text-muted hover:underline">
        {t("back")}
      </Link>
      <PageHeader title={t("title")} description={t("pageIntro")} />
      {permissions.includes("documents:create") ? <ObjektakteImportRun /> : null}
      {permissions.includes("objektakte:read") ? (
        <PreviewImportRun canStart={permissions.includes("objektakte:approve")} />
      ) : null}
      {!permissions.includes("documents:create") && !permissions.includes("objektakte:read") ? (
        <p role="alert" className={ui.alert} data-testid="objektakte-import-forbidden">
          {t("noPermission")}
        </p>
      ) : null}
    </div>
  );
}
