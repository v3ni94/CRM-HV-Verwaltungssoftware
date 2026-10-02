import { getTranslations } from "next-intl/server";

import { OwnerRentalReporting, type ReportingUnit } from "@/components/portal/OwnerRentalReporting";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Eigentümerreporting für Kapitalanleger (GAF-34, P13-01): hinter Mandantenschalter und G3. */
export default async function OwnerReportingPage() {
  const t = await getTranslations("OwnerReporting");
  const response = await serverFetch("/api/v1/portal/owner/rental-reporting");
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
  const body = (await response.json()) as { items: ReportingUnit[]; note: string; allocability_note?: string; enabled: boolean };
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <OwnerRentalReporting items={body.items} note={body.note} allocabilityNote={body.allocability_note} enabled={body.enabled} />
    </div>
  );
}
