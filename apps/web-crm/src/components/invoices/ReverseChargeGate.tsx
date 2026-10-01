import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

/** GA08-01: release point § 13b UStG on a reverse charge incoming invoice. Display only:
 *  no automatic decision, posting or tax consequence. */
export function ReverseChargeGate({ reverseCharge }: { reverseCharge: boolean }) {
  const t = useTranslations("Invoices");
  if (!reverseCharge) return null;
  return (
    <section className={ui.notice} data-testid="reverse-charge-gate">
      <h2 className={ui.h2}>{t("reverseChargeGateTitle")}</h2>
      <p>{t("reverseChargeGateText")}</p>
    </section>
  );
}
