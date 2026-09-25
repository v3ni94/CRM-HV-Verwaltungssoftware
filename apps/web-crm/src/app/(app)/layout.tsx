import Link from "next/link";
import { appBuild, appVersion } from "@/lib/version";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { AiChatWidget } from "@/components/ai/AiChatWidget";
import { MobileNav } from "@/components/shell/MobileNav";
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
        { href: "/start", label: t("dashboard"), icon: "dashboard" },
        ...(can("properties:read") ? [{ href: "/objekte", label: t("properties"), icon: "properties" }] : []),
        { href: "/kontakte", label: t("contacts"), icon: "contacts" },
        { href: "/kalender", label: t("calendar"), icon: "calendar" },
      ],
    },
    {
      label: t("group.management"),
      items: [
        ...(can("properties:read") ? [{ href: "/objekte?art=rental", label: t("rental"), icon: "rental" }] : []),
        ...(can("accounting:read") ? [{ href: "/weg", label: t("hoa"), icon: "hoa" }] : []),
        ...(can("properties:read") ? [{ href: "/objekte?art=sev", label: t("sev"), icon: "sev" }] : []),
        ...(can("contracts:read") ? [{ href: "/vermietung", label: t("letting"), icon: "letting" }] : []),
        ...(can("contracts:read") ? [{ href: "/makler", label: t("broker"), icon: "broker" }] : []),
        ...(can("documents:read") ? [{ href: "/dms", label: t("dms"), icon: "dms" }] : []),
        ...(can("tickets:read") ? [{ href: "/tickets", label: t("tickets"), icon: "tickets" }] : []),
        ...(can("communication:read") ? [{ href: "/mail", label: t("mail"), icon: "mail" }] : []),
      ],
    },
    {
      label: t("group.finance"),
      items: can("accounting:read")
        ? [
            { href: "/buchhaltung", label: t("accounting"), icon: "accounting" },
            { href: "/abrechnung", label: t("billing"), icon: "billing" },
            { href: "/rechnungen", label: t("invoices"), icon: "invoices" },
            { href: "/bank", label: t("bank"), icon: "bank" },
          ]
        : [],
    },
    {
      label: t("group.system"),
      items: [
        { href: "/assistent", label: t("assistant"), icon: "assistant" },
        { href: "/importe", label: t("imports"), icon: "imports" },
        { href: "/einstellungen", label: t("settings"), icon: "settings" },
        ...(me?.is_platform_admin ? [{ href: "/plattform", label: t("platform"), icon: "platform" }] : []),
      ],
    },
  ].filter((g) => g.items.length > 0);
  return (
    <div className="flex min-h-screen flex-col bg-surface md:flex-row">
      <a href="#inhalt" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50">
        {t("skip")}
      </a>
      <Suspense fallback={null}>
        <SideNav
          groups={groups}
          label={t("nav")}
          logoSrc="/logo-mhag.png"
          productName={tHome("productName")}
          area={tHome("area")}
          collapseLabel={t("navCollapse")}
          expandLabel={t("navExpand")}
        />
      </Suspense>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex flex-wrap items-center gap-2 border-b border-border bg-bg/80 px-4 py-2.5 backdrop-blur-md md:px-6">
          <MobileNav
            groups={groups}
            label={t("nav")}
            openLabel={t("openNav")}
            closeLabel={t("close")}
            productName={tHome("productName")}
            area={tHome("area")}
          />
          <SearchDialog />
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <NotificationBell />
            <ThemeToggle />
            <TenantSwitcher tenants={ctx.tenants} current={ctx.tenantId} />
            <UserMenu name={me?.display_name || me?.email || ""} email={me?.email ?? undefined} />
          </div>
        </header>
        <main id="inhalt" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 md:px-8 md:py-10">
          {children}
        </main>
        <footer
          className="border-t border-border-soft px-4 py-4 text-xs text-subtle md:px-8"
          style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}
        >
          <span>{tHome("footer")}</span>
          <span className="mt-1 block">
            <Link href="/version" className="underline-offset-2 hover:underline">
              Version {appVersion()}
              {appBuild() ? ` (${appBuild()})` : ""}
            </Link>
          </span>
        </footer>
      </div>
      <AiChatWidget />
    </div>
  );
}
