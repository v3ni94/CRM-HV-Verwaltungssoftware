import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { InstallHint } from "@/components/shell/InstallHint";
import { LogoutButton } from "@/components/shell/LogoutButton";
import { PortalNav } from "@/components/shell/PortalNav";
import type { Me } from "@/components/portal/types";
import { serverApi } from "@/lib/api-server";

/** Signed-in area of the portal: slim header with role aware navigation, content, footer note.
 *  A failed /me (e.g. session boundary) falls back to the tenant/owner navigation; the pages
 *  themselves enforce access via the API. */
async function currentMe(): Promise<Me | null> {
  try {
    const { data } = await serverApi().GET("/api/v1/portal/me");
    return (data as unknown as Me) ?? null;
  } catch {
    return null;
  }
}

/** Signed-in area of the portal: slim header, content, footer note. */
export default async function PortalLayout({ children }: { children: React.ReactNode }) {
  const [t, home, me] = await Promise.all([
    getTranslations("Portal"),
    getTranslations("Home"),
    currentMe(),
  ]);
  const provider = Boolean(me?.roles.includes("provider"));
  // A52: a pure board account (no contract of its own) sees only the audit room.
  const board = Boolean(me?.roles.includes("board"));
  const boardOnly = board && !me?.roles.some((role) => role !== "board");
  const links: { href: string; label: string }[] = provider
    ? [{ href: "/auftraege", label: t("nav.orders") }]
    : boardOnly
      ? [{ href: "/pruefung", label: t("nav.audit") }]
      : [
        { href: "/dokumente", label: t("nav.documents") },
        { href: "/aushaenge", label: t("nav.notices") },
        { href: "/meldungen", label: t("nav.tickets") },
        { href: "/formulare", label: t("nav.forms") },
        { href: "/konto", label: t("nav.account") },
        { href: "/zaehlerstand", label: t("nav.meter") },
        { href: "/daten", label: t("nav.data") },
        // A51: owner pages (read only), shown only with the owner role.
        ...(me?.roles.includes("owner")
          ? [
              { href: "/beschluesse", label: t("nav.resolutions") },
              { href: "/ansprechpartner", label: t("nav.contacts") },
              { href: "/hausgeldkonto", label: t("nav.hoaAccount") },
            ]
          : []),
        ...(board ? [{ href: "/pruefung", label: t("nav.audit") }] : []),
      ];
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-2 px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-baseline gap-3">
              <Link href="/start" className="text-sm font-semibold">
                {home("productName")}
              </Link>
              <span className="mhvp-label">{t("title")}</span>
            </div>
            <LogoutButton />
          </div>
          {/* O02: collapsible menu below md, horizontal row from md; active page marked. */}
          <PortalNav
            links={links}
            label={t("nav.label")}
            openLabel={t("nav.open")}
            closeLabel={t("nav.close")}
          />
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-5 px-4 py-6">
        <InstallHint />
        {children}
      </main>
      <footer className="mx-auto w-full max-w-4xl px-4 py-4 text-xs text-subtle">{t("footer")}</footer>
    </div>
  );
}
