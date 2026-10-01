import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { SettingsSearch } from "@/components/settings/SettingsSearch";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Settings hub (M-settings): card grid, visible per permission. Every card links to its own
 *  page which enforces the permission again server side. */
export default async function SettingsPage() {
  const t = await getTranslations("Settings");
  const tw = await getTranslations("Webhooks");
  const tm = await getTranslations("Metering");
  const tq = await getTranslations("SettingsQ05");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const can = (p: string) => me.data?.permissions.includes(p) ?? false;

  const cards = [
    { href: "/einstellungen/benutzer", title: t("members.title"), description: t("members.description"), show: can("members:read") },
    { href: "/einstellungen/rollen", title: t("roles.title"), description: t("roles.description"), show: can("roles:read") },
    { href: "/einstellungen/mandant", title: t("company.title"), description: t("company.description"), show: can("tenant_settings:read") },
    { href: "/einstellungen/ki", title: t("ai.title"), description: t("ai.description"), show: can("tenant_settings:update") },
    { href: "/einstellungen/wissen", title: t("knowledge.title"), description: t("knowledge.description"), show: can("tenant_settings:read") },
    { href: "/einstellungen/postfaecher", title: t("mail.title"), description: t("mail.description"), show: can("tenant_settings:update") },
    { href: "/einstellungen/dms", title: t("dms.title"), description: t("dms.description"), show: can("tenant_settings:update") },
    { href: "/einstellungen/aufbewahrung", title: t("retention.title"), description: t("retention.description"), show: can("tenant_settings:update") },
    { href: "/einstellungen/dokumentkategorien", title: t("documentCategories.title"), description: t("documentCategories.description"), show: can("tenant_settings:update") },
    { href: "/einstellungen/datenschutz", title: t("privacy.title"), description: t("privacy.description"), show: can("privacy:read") },
    { href: "/dokumente/loeschvorschlaege", title: t("deletionProposals.title"), description: t("deletionProposals.description"), show: can("documents:read") },
    { href: "/einstellungen/bank", title: t("bank.title"), description: t("bank.description"), show: can("tenant_settings:update") },
    { href: "/einstellungen/telefonie", title: t("telephony.title"), description: t("telephony.description"), show: can("tenant_settings:read") },
    { href: "/einstellungen/schnittstellen/messdienstleister", title: tm("card.title"), description: tm("card.description"), show: can("metering_data:read") },
    { href: "/einstellungen/webhooks", title: tw("card.title"), description: tw("card.description"), show: can("tenant_settings:update") },
    { href: "/einstellungen/weg", title: t("weg.title"), description: t("weg.description"), show: can("accounting:read") },
    { href: "/einstellungen/datenqualitaet", title: t("dataQuality.title"), description: t("dataQuality.description"), show: can("contacts:read") },
    { href: "/einstellungen/kataloge", title: t("catalogs.title"), description: t("catalogs.description"), show: can("properties:read") },
    { href: "/einstellungen/felder", title: t("customFields.title"), description: t("customFields.description"), show: can("properties:read") },
    { href: "/einstellungen/kautionszinsen", title: t("depositRates.title"), description: t("depositRates.description"), show: can("contracts:read") },
    { href: "/einstellungen/fristtypen", title: t("deadlineTypes.title"), description: t("deadlineTypes.description"), show: can("tenant_settings:read") },
    { href: "/einstellungen/sla", title: t("sla.title"), description: t("sla.description"), show: can("sla:read") },
    {
      href: "/einstellungen/ticketvorlagen",
      title: t("ticketTemplates.title"),
      description: t("ticketTemplates.description"),
      show: can("tickets:read"),
    },
    {
      href: "/einstellungen/portalformulare",
      title: t("portalForms.title"),
      description: t("portalForms.description"),
      show: can("tickets:read"),
    },
    {
      href: "/einstellungen/automatisierung",
      title: t("automation.title"),
      description: t("automation.description"),
      show: can("tenant_settings:read") || can("tickets:read"),
    },
    {
      href: "/einstellungen/regelvorschlaege",
      title: t("ruleProposals.title"),
      description: t("ruleProposals.description"),
      show: can("tenant_settings:read"),
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
    {
      href: "/einstellungen/buchhaltung/kontenrahmen",
      title: t("chartRelease.title"),
      description: t("chartRelease.description"),
      show: can("accounting:read"),
    },
    {
      href: "/einstellungen/buchhaltung/g1-oeffnung",
      title: t("g1Opening.title"),
      description: t("g1Opening.description"),
      show: can("accounting:read"),
    },
    {
      href: "/einstellungen/buchhaltung/steuern",
      title: t("taxes.title"),
      description: t("taxes.description"),
      show: can("tenant_settings:read"),
    },
    { href: "/einstellungen/immoware", title: t("immoware.title"), description: t("immoware.description"), show: can("immoware:read") },
    {
      href: "/einstellungen/objektakte",
      title: t("objektakte.title"),
      description: t("objektakte.description"),
      show: can("documents:read"),
    },
    { href: "/einstellungen/teams", title: tq("teams.title"), description: tq("teams.description"), show: can("tickets:read") },
    { href: "/einstellungen/kontakt-tags", title: tq("contactTags.title"), description: tq("contactTags.description"), show: can("contacts:read") },
    { href: "/einstellungen/profil", title: t("profile.title"), description: t("profile.description"), show: true },
    { href: "/plattform", title: t("platform.title"), description: t("platform.description"), show: Boolean(me.data?.is_platform_admin) },
  ].filter((c) => c.show);

  const permissions = me.data?.permissions ?? [];

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <SettingsSearch permissions={permissions} />
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
