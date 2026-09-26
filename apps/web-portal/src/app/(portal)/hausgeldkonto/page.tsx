import { getTranslations } from "next-intl/server";

import { HoaAccountTable } from "@/components/portal/HoaAccountTable";
import type { HoaAccount } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Hausgeldkonto (A51, Rolle Eigentümer): gebuchte Sollstellungen und Zahlungen aus dem
 *  Buchungskreis der Gemeinschaft, Beträge in 1.234,56 EUR, Daten in TT.MM.JJJJ. Keine
 *  Abrechnung, keine Rechtsfolge. */
export default async function HoaAccountPage() {
  const t = await getTranslations("HoaAccount");
  const response = await serverFetch("/api/v1/portal/hoa-account");
  redirectIfUnauthenticated(response);
  if (response.status === 403) {
    return (
      <div className={ui.pageGap}>
        <h1 className={ui.title}>{t("title")}</h1>
        <p className={ui.notice}>{t("ownersOnly")}</p>
      </div>
    );
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const account = (await response.json()) as HoaAccount;
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <HoaAccountTable account={account} />
    </div>
  );
}
