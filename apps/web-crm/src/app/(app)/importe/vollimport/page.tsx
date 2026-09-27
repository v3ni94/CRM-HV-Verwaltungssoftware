import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { FullImport } from "@/components/imports/FullImport";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Same permissions as /imports/immoware24/vollimport: ai:create plus the domain permissions. */
const FULL_IMPORT_PERMISSIONS = ["ai:create", "properties:create", "contacts:create", "contracts:create"];

/** Vollimport mit Stichtag (M8-01, M8-02, V9): Vorprüfung, Trockenlauf, Übernahme, Abgleichbericht. */
export default async function FullImportPage() {
  const t = await getTranslations("FullImport");
  const me = await serverApi().GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  const allowed = FULL_IMPORT_PERMISSIONS.every((p) => permissions.includes(p));
  return (
    <div className="flex flex-col gap-4">
      <Link href="/importe" className="text-sm text-muted hover:underline">
        {t("backToImports")}
      </Link>
      <PageHeader title={t("title")} />
      {allowed ? (
        <FullImport />
      ) : (
        <p role="alert" className={ui.alert} data-testid="fullimport-forbidden">
          {t("noPermission")}
        </p>
      )}
    </div>
  );
}
