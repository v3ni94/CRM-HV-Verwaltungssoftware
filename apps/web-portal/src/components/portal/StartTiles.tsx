"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

import type { Me } from "@/components/portal/types";
import { ui } from "@/lib/ui";

/** Rollenabhängige Kacheln der Startseite: Dienstleister sehen nur ihre Aufträge, Mieter und
 *  Eigentümer sehen Dokumente, Meldungen, Kontoauszug, Zählerstand und Datenänderung. */
export function StartTiles({ me, newNotices = 0 }: { me: Me; newNotices?: number }) {
  const t = useTranslations("Portal");
  const provider = me.roles.includes("provider");
  // A52: a pure board account (no contract of its own) sees only the audit room.
  const board = me.roles.includes("board");
  const boardOnly = board && !me.roles.some((role) => role !== "board");
  const tiles: { href: string; label: string }[] = provider
    ? [{ href: "/auftraege", label: t("start.orders") }]
    : boardOnly
      ? [{ href: "/pruefung", label: t("start.audit") }]
      : [
        { href: "/dokumente", label: t("start.documents") },
        { href: "/aushaenge", label: t("start.notices") },
        { href: "/meldungen", label: t("start.tickets") },
        { href: "/formulare", label: t("start.forms") },
        { href: "/konto", label: t("start.account") },
        { href: "/zaehlerstand", label: t("start.meter") },
        { href: "/daten", label: t("start.data") },
        { href: "/uebergabe", label: t("start.handover") },
        // A51: owner tiles (read only), owners only.
        ...(me.roles.includes("owner")
          ? [
              { href: "/beschluesse", label: t("start.resolutions") },
              { href: "/ansprechpartner", label: t("start.contacts") },
              { href: "/hausgeldkonto", label: t("start.hoaAccount") },
            ]
          : []),
        ...(board ? [{ href: "/pruefung", label: t("start.audit") }] : []),
      ];
  return (
    <div className={ui.pageGap}>
      <p className="text-sm text-muted">
        {provider ? t("start.greetingProvider") : boardOnly ? t("start.greetingBoard") : t("start.greetingTenantOwner")}
      </p>
      {!provider && newNotices > 0 ? (
        <p className={ui.notice} data-testid="new-notices">
          <Link href="/aushaenge" className="hover:underline">
            {t("start.newNotices", { count: newNotices })}
          </Link>
        </p>
      ) : null}
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
