import { getTranslations } from "next-intl/server";

import { OwnerOverview } from "@/components/portal/OwnerOverview";
import type { OwnerAllocationUnit, OwnerRentalIncome, OwnerTicket, PaymentResolution } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Eigentümerübersicht (M21-06, SA-05): beschlossene Zahlungen und freigegebene Meldungen,
 *  lesend; nur mit Eigentümerrolle oder Vollmacht (sonst 403 der API). */
export default async function OwnerOverviewPage() {
  const t = await getTranslations("OwnerOverview");
  const [payments, tickets, allocations, income] = await Promise.all([
    serverFetch("/api/v1/portal/owner/payment-resolutions"),
    serverFetch("/api/v1/portal/owner/tickets"),
    serverFetch("/api/v1/portal/owner/allocation-properties"),
    serverFetch("/api/v1/portal/owner/rental-income"),
  ]);
  redirectIfUnauthenticated(payments);
  if (payments.status === 403) {
    return (
      <div className={ui.pageGap}>
        <h1 className={ui.title}>{t("title")}</h1>
        <p className={ui.notice}>{t("ownersOnly")}</p>
      </div>
    );
  }
  if (!payments.ok) throw new Error(`HTTP ${payments.status}`);
  const paymentData = (await payments.json()) as { items: PaymentResolution[]; note: string };
  const ticketData = tickets.ok ? ((await tickets.json()) as OwnerTicket[]) : [];
  const allocationData = allocations.ok
    ? ((await allocations.json()) as { items: OwnerAllocationUnit[] }).items
    : [];
  const incomeData = income.ok ? ((await income.json()) as { items: OwnerRentalIncome[] }).items : [];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <OwnerOverview
        payments={paymentData.items}
        note={paymentData.note}
        tickets={ticketData}
        allocations={allocationData}
        income={incomeData}
      />
    </div>
  );
}
