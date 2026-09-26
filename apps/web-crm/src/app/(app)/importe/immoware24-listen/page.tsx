import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { ListImports } from "@/components/imports/ListImports";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Same permissions as the API endpoints /imports/immoware24/lists/*: ai:create plus the domain
 *  permissions for properties, contacts and contracts. */
const LIST_IMPORT_PERMISSIONS = ["ai:create", "properties:create", "contacts:create", "contracts:create"];

/** Immoware24 Listenimport: Objektdaten, Kontakte und Zuordnung als Upload im Browser. */
export default async function Immoware24ListsPage() {
  const t = await getTranslations("ImmowareLists");
  const me = await serverApi().GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  const allowed = LIST_IMPORT_PERMISSIONS.every((p) => permissions.includes(p));
  return (
    <div className="flex flex-col gap-4">
      <Link href="/importe" className="text-sm text-muted hover:underline">
        {t("backToImports")}
      </Link>
      <PageHeader title={t("title")} />
      {allowed ? (
        <ListImports />
      ) : (
        <p role="alert" className={ui.alert} data-testid="immoware-lists-forbidden">
          {t("noPermission")}
        </p>
      )}
    </div>
  );
}
