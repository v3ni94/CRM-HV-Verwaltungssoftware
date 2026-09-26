import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Settings hub (M-settings): card grid, visible per permission. Every card links to its own
 *  page which enforces the permission again server side. */
export default async function SettingsPage() {
  const t = await getTranslations("Settings");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const can = (p: string) => me.data?.permissions.includes(p) ?? false;

  const cards = [
    { href: "/einstellungen/benutzer", title: t("members.title"), description: t("members.description"), show: can("members:read") },
    { href: "/einstellungen/rollen", title: t("roles.title"), description: t("roles.description"), show: can("roles:read") },
    { href: "/einstellungen/mandant", title: t("company.title"), description: t("company.description"), show: can("tenant_settings:read") },
    { href: "/einstellungen/ki", title: t("ai.title"), description: t("ai.description"), show: can("tenant_settings:update") },
    { href: "/einstellungen/postfaecher", title: t("mail.title"), description: t("mail.description"), show: can("tenant_settings:update") },
    { href: "/einstellungen/dms", title: t("dms.title"), description: t("dms.description"), show: can("tenant_settings:update") },
    { href: "/einstellungen/bank", title: t("bank.title"), description: t("bank.description"), show: can("tenant_settings:update") },
    { href: "/einstellungen/weg", title: t("weg.title"), description: t("weg.description"), show: can("accounting:read") },
    { href: "/einstellungen/sla", title: t("sla.title"), description: t("sla.description"), show: can("sla:read") },
    {
      href: "/einstellungen/ticketvorlagen",
      title: t("ticketTemplates.title"),
      description: t("ticketTemplates.description"),
      show: can("tickets:read"),
    },
    {
      href: "/einstellungen/automatisierung",
      title: t("automation.title"),
      description: t("automation.description"),
      show: can("tenant_settings:read") || can("tickets:read"),
    },
    {
      href: "/einstellungen/antwortvorlagen",
      title: t("replyTemplates.title"),
      description: t("replyTemplates.description"),
      show: can("tickets:read"),
    },
    {
      href: "/einstellungen/buchhaltung/datev",
      title: t("datev.title"),
      description: t("datev.description"),
      show: can("accounting:read"),
    },
    { href: "/einstellungen/immoware", title: t("immoware.title"), description: t("immoware.description"), show: can("immoware:read") },
    {
      href: "/einstellungen/objektakte",
      title: t("objektakte.title"),
      description: t("objektakte.description"),
      show: can("documents:read"),
    },
    { href: "/einstellungen/profil", title: t("profile.title"), description: t("profile.description"), show: true },
    { href: "/plattform", title: t("platform.title"), description: t("platform.description"), show: Boolean(me.data?.is_platform_admin) },
  ].filter((c) => c.show);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((c) => (
          <Link key={c.href} href={c.href} className={ui.cardLink}>
            <h2 className={ui.h2}>{c.title}</h2>
            <p className="mt-1 text-sm text-muted">{c.description}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
