import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { ApiKeysAdmin, type ApiKeyRow } from "@/components/settings/ApiKeysAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** API keys of the tenant (AF19): prefix only, revoke, key shown once at creation. */
export default async function ApiKeysPage() {
  const t = await getTranslations("AF19");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("api_keys:read")) notFound();
  const res = await serverFetch("/api/v1/tenant/api-keys");
  const initial: ApiKeyRow[] = res.ok ? ((await res.json()) as ApiKeyRow[]) : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("keys.title")} description={t("keys.intro")} />
      <ApiKeysAdmin
        initial={initial}
        loadFailed={!res.ok}
        canCreate={permissions.includes("api_keys:create")}
        canDelete={permissions.includes("api_keys:delete")}
        ownPermissions={permissions}
      />
    </div>
  );
}
