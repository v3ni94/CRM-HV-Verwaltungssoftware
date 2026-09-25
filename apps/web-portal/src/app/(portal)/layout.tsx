import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { LogoutButton } from "@/components/shell/LogoutButton";
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
  const links: { href: string; label: string }[] = provider
    ? [{ href: "/auftraege", label: t("nav.orders") }]
    : [
        { href: "/dokumente", label: t("nav.documents") },
        { href: "/meldungen", label: t("nav.tickets") },
        { href: "/konto", label: t("nav.account") },
        { href: "/zaehlerstand", label: t("nav.meter") },
        { href: "/daten", label: t("nav.data") },
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
          <nav className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {links.map((link) => (
              <Link key={link.href} href={link.href} className="text-muted hover:text-fg hover:underline">
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-5 px-4 py-6">{children}</main>
      <footer className="mx-auto w-full max-w-4xl px-4 py-4 text-xs text-subtle">{t("footer")}</footer>
    </div>
  );
}
