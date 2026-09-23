import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { SearchDialog } from "@/components/shell/SearchDialog";
import { TenantSwitcher } from "@/components/shell/TenantSwitcher";
import { UserMenu } from "@/components/shell/UserMenu";
import { redirectIfUnauthenticated, serverApi, sessionContext } from "@/lib/api-server";

export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const [t, tHome, ctx] = await Promise.all([
    getTranslations("Shell"),
    getTranslations("Home"),
    sessionContext(),
  ]);
  const { data: me, response } = await serverApi().GET("/api/v1/auth/me");
  redirectIfUnauthenticated(response);
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#inhalt" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2">
        {t("skip")}
      </a>
      <header className="flex flex-wrap items-center gap-3 border-b border-border bg-surface px-4 py-2">
        <Link href="/kontakte" className="text-sm font-semibold">
          {tHome("productName")}
        </Link>
        <nav aria-label={t("nav")} className="flex gap-3 text-sm">
          <Link href="/kontakte" className="hover:underline">
            {t("contacts")}
          </Link>
          <Link href="/assistent" className="hover:underline">
            {t("assistant")}
          </Link>
          <Link href="/importe" className="hover:underline">
            {t("imports")}
          </Link>
          {me?.permissions.includes("tenant_settings:update") ? (
            <Link href="/einstellungen/ki" className="hover:underline">
              {t("aiSettings")}
            </Link>
          ) : null}
        </nav>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <SearchDialog />
          <TenantSwitcher tenants={ctx.tenants} current={ctx.tenantId} />
          <UserMenu name={me?.display_name || me?.email || ""} />
        </div>
      </header>
      <main id="inhalt" className="mx-auto w-full max-w-6xl flex-1 px-4 py-4">
        {children}
      </main>
    </div>
  );
}
