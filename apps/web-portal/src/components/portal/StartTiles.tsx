"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

import type { Me } from "@/components/portal/types";
import { ui } from "@/lib/ui";

/** Rollenabhängige Kacheln der Startseite: Dienstleister sehen nur ihre Aufträge, Mieter und
 *  Eigentümer sehen Dokumente, Meldungen, Kontoauszug, Zählerstand und Datenänderung. */
export function StartTiles({ me }: { me: Me }) {
  const t = useTranslations("Portal");
  const provider = me.roles.includes("provider");
  const tiles: { href: string; label: string }[] = provider
    ? [{ href: "/auftraege", label: t("start.orders") }]
    : [
        { href: "/dokumente", label: t("start.documents") },
        { href: "/meldungen", label: t("start.tickets") },
        { href: "/konto", label: t("start.account") },
        { href: "/zaehlerstand", label: t("start.meter") },
        { href: "/daten", label: t("start.data") },
        { href: "/uebergabe", label: t("start.handover") },
      ];
  return (
    <div className={ui.pageGap}>
      <p className="text-sm text-muted">
        {provider ? t("start.greetingProvider") : t("start.greetingTenantOwner")}
      </p>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {tiles.map((tile) => (
          <li key={tile.href}>
            <Link href={tile.href} className={ui.cardLink}>
              {tile.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
