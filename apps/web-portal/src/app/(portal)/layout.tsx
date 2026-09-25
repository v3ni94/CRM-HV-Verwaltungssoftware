import { getTranslations } from "next-intl/server";

import { Topbar, type NavItem } from "@/components/layout/Topbar";
import { redirectIfUnauthenticated, serverGet } from "@/lib/api-server";
import { hasContracts, isProvider, type PortalMe } from "@/lib/portal";

export const dynamic = "force-dynamic";

export default async function PortalLayout({ children }: { children: React.ReactNode }) {
  const t = await getTranslations("Shell");
  const { data: me, response } = await serverGet<PortalMe>("/api/v1/portal/me");
  redirectIfUnauthenticated(response);
  const items: NavItem[] = [
    { href: "/", label: t("navStart") },
    { href: "/dokumente", label: t("navDocuments") },
    { href: "/anliegen", label: t("navTickets") },
    ...(me && hasContracts(me)
      ? [
          { href: "/zaehlerstand", label: t("navMeter") },
          { href: "/konto", label: t("navAccount") },
        ]
      : []),
    ...(me && isProvider(me) ? [{ href: "/auftraege", label: t("navOrders") }] : []),
  ];
  return (
    <div className="flex min-h-screen flex-col">
      <Topbar items={items} />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>
    </div>
  );
}
