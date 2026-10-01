import { cookies } from "next/headers";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { redirect } from "next/navigation";

import { InstallHint } from "@/components/shell/InstallHint";
import { LogoutButton } from "@/components/shell/LogoutButton";
import { RoleSwitcher } from "@/components/shell/RoleSwitcher";
import { PortalNav } from "@/components/shell/PortalNav";
import { LanguageSwitch } from "@/components/shell/LanguageSwitch";
import { ThemeSwitch } from "@/components/shell/ThemeToggle";
import { type Me, showsHandover } from "@/components/portal/types";
import { BrandMark, LegalLinks } from "@/components/shell/Branding";
import { serverApi, serverFetch } from "@/lib/api-server";
import { fetchPortalBranding } from "@/lib/branding";

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

/** AC06 (GA02-06): with a published terms version the portal needs its acceptance
 *  (MHVP-CONT-0020); the layout sends the account to the acceptance mask. A failed query
 *  never blocks the page, the API enforces the rule on every call. */
async function termsPending(): Promise<boolean> {
  try {
    const response = await serverFetch("/api/v1/portal/terms");
    if (!response.ok) return false;
    const status = (await response.json()) as { terms_version?: string | null; accepted?: boolean };
    return Boolean(status.terms_version) && status.accepted === false;
  } catch {
    return false;
  }
}

/** Signed-in area of the portal: slim header, content, footer note. */
export default async function PortalLayout({ children }: { children: React.ReactNode }) {
  if (await termsPending()) redirect("/nutzungsbedingungen");
  const [t, home, me, branding] = await Promise.all([
    getTranslations("Portal"),
    getTranslations("Home"),
    currentMe(),
    fetchPortalBranding(),
  ]);
  // M21-05, S16-10: an account with several portal roles may narrow the navigation to one of
  // them (cookie); an unknown value is ignored. This grants nothing, the API decides access.
  const portalRoles = me?.portal_roles ?? [];
  const requested = (await cookies()).get("portal_view")?.value ?? null;
  const view = requested && portalRoles.includes(requested) ? requested : null;
  const provider = view ? view === "service_provider" : Boolean(me?.roles.includes("provider"));
  // A52: a pure board account (no contract of its own) sees only the audit room.
  const board = Boolean(me?.roles.includes("board"));
  const boardOnly = board && !me?.roles.some((role) => role !== "board");
  const links: { href: string; label: string }[] = provider
    ? [
        { href: "/auftraege", label: t("nav.orders") },
        { href: "/rahmenvertraege", label: t("nav.framework") },
      ]
    : boardOnly
      ? [{ href: "/pruefung", label: t("nav.audit") }]
      : [
        { href: "/dokumente", label: t("nav.documents") },
        { href: "/aushaenge", label: t("nav.notices") },
        { href: "/meldungen", label: t("nav.tickets") },
        { href: "/formulare", label: t("nav.forms") },
        // AE28: Assistent für die eigenen Unterlagen, nur bei eingeschaltetem Chat-Bot des Mandanten.
        ...(me?.features?.chat_bot_enabled ? [{ href: "/assistent", label: t("nav.assistant") }] : []),
        { href: "/konto", label: t("nav.account") },
        { href: "/zaehlerstand", label: t("nav.meter") },
        { href: "/verbrauch", label: t("nav.consumption") },
        { href: "/daten", label: t("nav.data") },
        { href: "/lastschrift", label: t("nav.mandate") },
        // M31 WP5: Übergabeprotokoll for helpers, participants, tenants and owners with a grant
        // (same rule as the start tile, showsHandover), so the protocol stays one tap away.
        ...(me && showsHandover(me) ? [{ href: "/uebergabe", label: t("nav.handover") }] : []),
        // A51: owner pages (read only), shown only with the owner role.
        ...(me?.roles.includes("owner") && (!view || view === "owner" || view === "board_member" || view === "representative")
          ? [
              { href: "/beschluesse", label: t("nav.resolutions") },
              { href: "/versammlungen", label: t("nav.meetings") },
              { href: "/ansprechpartner", label: t("nav.contacts") },
              { href: "/hausgeldkonto", label: t("nav.hoaAccount") },
              { href: "/abrechnungen", label: t("nav.ownerStatements") },
              { href: "/eigentum", label: t("nav.ownerOverview") },
            ]
          : []),
        // M21-05: representatives see their powers of attorney with the period.
        ...(portalRoles.includes("representative") ? [{ href: "/vertretung", label: t("nav.representation") }] : []),
        ...(board ? [{ href: "/pruefung", label: t("nav.audit") }] : []),
        // M19-02: submissions to the board (owner with the board contact category, or board role).
        ...(me?.roles.includes("owner") || board ? [{ href: "/vorlagen", label: t("nav.submissions") }] : []),
      ];
  // Sicherheit (optional second factor, remembered devices) is available to every account.
  links.push({ href: "/sicherheit", label: t("nav.security") });
  return (
    <div className="flex min-h-screen flex-col">
      {/* V13: skip link, only visible on keyboard focus, jumps past header and navigation. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-fg focus:ring-2 focus:ring-focus"
      >
        {t("skipToContent")}
      </a>
      <header className="border-b border-border bg-surface-2">
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-2 px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
            <div className="flex items-baseline gap-3">
              <Link href="/start" className="text-sm font-semibold">
                {branding.hasLogoLight || branding.hasLogoDark ? (
                  <BrandMark branding={branding} fallback={home("productName")} />
                ) : (
                  (branding.name ?? home("productName"))
                )}
              </Link>
              <span className="mhvp-label">{t("title")}</span>
            </div>
            {/* Darstellung Hell, Dunkel, Automatisch (stored in this browser) next to Abmelden. */}
            <div className="flex flex-wrap items-center gap-2">
              <RoleSwitcher roles={portalRoles} current={view} />
              <LanguageSwitch />
              <ThemeSwitch />
              <LogoutButton />
            </div>
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
      <main id="main-content" tabIndex={-1} className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-5 px-4 py-6">
        <InstallHint />
        {children}
      </main>
      <footer
        className="mx-auto w-full max-w-4xl px-4 py-4 text-xs text-subtle"
        /* Above the home indicator of an installed app (M31 WP5). */
        style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}
      >
        {t("footer")} <Link href="/barrierefreiheit" className="underline hover:text-fg">{t("accessibilityLink")}</Link>
        <LegalLinks branding={branding} />
      </footer>
    </div>
  );
}
