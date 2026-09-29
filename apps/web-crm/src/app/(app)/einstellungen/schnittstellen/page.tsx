import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Schnittstellen hub (Einstellungen → Schnittstellen): external systems of the tenant. */
export default async function InterfacesPage() {
  const t = await getTranslations("Metering");
  const ts = await getTranslations("Settings");
  const tw = await getTranslations("Webhooks");
  const tsd = await getTranslations("Schadenstool");
  const tlx = await getTranslations("Lexoffice");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const can = (p: string) => me.data?.permissions.includes(p) ?? false;
  const cards = [
    { href: "/einstellungen/schnittstellen/messdienstleister", title: t("card.title"), description: t("card.description"), show: can("metering_data:read") },
    { href: "/einstellungen/schnittstellen/schadenbearbeiter", title: tsd("card.title"), description: tsd("card.description"), show: can("tenant_settings:read") },
    { href: "/einstellungen/schnittstellen/lexware-office", title: tlx("card.title"), description: tlx("card.description"), show: can("tenant_settings:read") },
    { href: "/einstellungen/webhooks", title: tw("card.title"), description: tw("card.description"), show: can("tenant_settings:update") },
    { href: "/einstellungen/immoware", title: ts("immoware.title"), description: ts("immoware.description"), show: can("immoware:read") },
  ].filter((c) => c.show);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/einstellungen", label: ts("title") }, { label: t("interfaces") }]} title={t("interfaces")} />
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
