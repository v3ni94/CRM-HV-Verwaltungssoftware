import { getTranslations } from "next-intl/server";

import { TenantPicker } from "@/components/auth/TenantPicker";
import { AuthCard } from "@/components/layout/AuthCard";
import { sessionContext } from "@/lib/api-server";

export const dynamic = "force-dynamic";

export default async function TenantPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const [t, ctx, { next }] = await Promise.all([getTranslations("Auth"), sessionContext(), searchParams]);
  const target = next && next.startsWith("/") && !next.startsWith("//") ? next : "/kontakte";
  return (
    <AuthCard title={t("tenantTitle")}>
      {ctx.tenants.length ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted">{t("tenantHint")}</p>
          <TenantPicker tenants={ctx.tenants} next={target} />
        </div>
      ) : (
        <p className="text-sm">{t("noTenants")}</p>
      )}
    </AuthCard>
  );
}
