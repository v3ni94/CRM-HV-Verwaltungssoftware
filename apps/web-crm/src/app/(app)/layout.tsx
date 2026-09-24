import { getTranslations } from "next-intl/server";
import { Suspense } from "react";
import Image from "next/image";
import Link from "next/link";

import { AiChatWidget } from "@/components/ai/AiChatWidget";
import { SearchDialog } from "@/components/shell/SearchDialog";
import { SideNav, type NavGroup } from "@/components/shell/SideNav";
import { TenantSwitcher } from "@/components/shell/TenantSwitcher";
import { UserMenu } from "@/components/shell/UserMenu";
import { NotificationBell } from "@/components/workspace/NotificationBell";
import { ThemeToggle } from "@/components/workspace/ThemeToggle";
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
  const can = (p: string) => me?.permissions.includes(p) ?? false;
  const groups: NavGroup[] = [
    {
      label: t("group.overview"),
      items: [
        { href: "/start", label: t("dashboard") },
        ...(can("properties:read") ? [{ href: "/objekte", label: t("properties") }] : []),
        { href: "/kontakte", label: t("contacts") },
        { href: "/kalender", label: t("calendar") },
      ],
    },
    {
      label: t("group.management"),
      items: [
        ...(can("properties:read") ? [{ href: "/objekte?art=rental", label: t("rental") }] : []),
        ...(can("accounting:read") ? [{ href: "/weg", label: t("hoa") }] : []),
        ...(can("properties:read") ? [{ href: "/objekte?art=sev", label: t("sev") }] : []),
        ...(can("contracts:read") ? [{ href: "/vermietung", label: t("letting") }] : []),
        ...(can("contracts:read") ? [{ href: "/makler", label: t("broker") }] : []),
        ...(can("tickets:read") ? [{ href: "/tickets", label: t("tickets") }] : []),
      ],
    },
    {
      label: t("group.finance"),
      items: can("accounting:read")
        ? [
            { href: "/buchhaltung", label: t("accounting") },
            { href: "/abrechnung", label: t("billing") },
            { href: "/rechnungen", label: t("invoices") },
            { href: "/bank", label: t("bank") },
          ]
        : [],
    },
    {
      label: t("group.system"),
      items: [
        { href: "/assistent", label: t("assistant") },
        { href: "/importe", label: t("imports") },
        { href: "/einstellungen", label: t("settings") },
        ...(me?.is_platform_admin ? [{ href: "/plattform", label: t("platform") }] : []),
      ],
    },
  ].filter((g) => g.items.length > 0);
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <a href="#inhalt" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50">
        {t("skip")}
      </a>
      <aside className="flex flex-col border-b border-border bg-surface md:sticky md:top-0 md:h-screen md:w-60 md:shrink-0 md:border-b-0 md:border-r">
        <Link href="/start" className="flex items-center gap-3 border-b border-border px-4 py-3 md:py-4">
          <Image src="/logo-mhag.png" alt="" width={44} height={38} unoptimized priority className="h-9 w-auto" />
          <span className="flex flex-col leading-tight">
            <span className="text-sm font-semibold">{tHome("productName")}</span>
            <span className="mhvp-label">{tHome("area")}</span>
          </span>
        </Link>
        <Suspense fallback={null}>
          <SideNav groups={groups} label={t("nav")} />
        </Suspense>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex flex-wrap items-center gap-2 border-b border-border bg-bg/80 px-4 py-2.5 backdrop-blur-md">
          <SearchDialog />
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <NotificationBell />
            <ThemeToggle />
            <TenantSwitcher tenants={ctx.tenants} current={ctx.tenantId} />
            <UserMenu name={me?.display_name || me?.email || ""} email={me?.email ?? undefined} />
          </div>
        </header>
        <main id="inhalt" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8">
          {children}
        </main>
        <footer className="border-t border-border px-4 py-3 text-xs text-subtle md:px-8">{tHome("footer")}</footer>
      </div>
      <AiChatWidget />
    </div>
  );
}
