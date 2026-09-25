import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { redirectIfUnauthenticated, serverGet } from "@/lib/api-server";
import { hasContracts, isProvider, type PortalMe } from "@/lib/portal";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Card = { href: string; title: string; text: string };

export default async function StartPage() {
  const t = await getTranslations("Start");
  const { data: me, response } = await serverGet<PortalMe>("/api/v1/portal/me");
  redirectIfUnauthenticated(response);
  const cards: Card[] = [
    { href: "/dokumente", title: t("cardDocuments"), text: t("cardDocumentsText") },
    { href: "/anliegen", title: t("cardTickets"), text: t("cardTicketsText") },
    ...(me && hasContracts(me)
      ? [
          { href: "/zaehlerstand", title: t("cardMeter"), text: t("cardMeterText") },
          { href: "/konto", title: t("cardAccount"), text: t("cardAccountText") },
        ]
      : []),
    ...(me && isProvider(me) ? [{ href: "/auftraege", title: t("cardOrders"), text: t("cardOrdersText") }] : []),
  ];
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className={ui.title}>{t("greeting")}</h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">{t("intro")}</p>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((card) => (
          <Link key={card.href} href={card.href} className={ui.cardLink}>
            <h2 className={ui.h2}>{card.title}</h2>
            <p className="mt-2 text-sm text-muted">{card.text}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
