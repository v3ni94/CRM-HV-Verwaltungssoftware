import Link from "next/link";
import { getTranslations } from "next-intl/server";

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
    { href: "/einstellungen/profil", title: t("profile.title"), description: t("profile.description"), show: true },
    { href: "/plattform", title: t("platform.title"), description: t("platform.description"), show: Boolean(me.data?.is_platform_admin) },
  ].filter((c) => c.show);

  return (
    <div className="flex flex-col gap-4">
      <h1 className={ui.title}>{t("title")}</h1>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((c) => (
          <Link key={c.href} href={c.href} className={ui.cardLink}>
            <h2 className="font-medium">{c.title}</h2>
            <p className="mt-1 text-sm text-muted">{c.description}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
