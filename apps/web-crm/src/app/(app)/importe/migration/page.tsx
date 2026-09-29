import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { MigrationStatus } from "@/components/imports/MigrationStatus";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Migration von Immoware24 ohne Parallelbetrieb (6.9.10, M8-03): Status je Objekt,
 * Migrationsjournal, Eröffnungssalden mit Freigabe, Abgleich, Wechsel des führenden Systems. */
export default async function MigrationPage() {
  const t = await getTranslations("Migration");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  return (
    <div className="flex flex-col gap-4">
      <Link href="/importe" className="text-sm text-muted hover:underline">
        {t("backToImports")}
      </Link>
      <PageHeader title={t("title")} description={t("pageIntro")} />
      {permissions.includes("accounting:read") ? (
        <MigrationStatus
          canCreate={permissions.includes("accounting:create")}
          canUpdate={permissions.includes("accounting:update")}
          canApprove={permissions.includes("accounting:approve")}
        />
      ) : (
        <p role="alert" className="rounded-md border border-danger-line bg-danger-bg px-3 py-2 text-sm text-danger-fg" data-testid="migration-forbidden">
          {t("noPermission")}
        </p>
      )}
    </div>
  );
}
