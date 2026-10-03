import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

/** GAM-206: Warnung "n Positionen veraltet" für Prüfauftrag, Prüfbericht und Beiratsabschnitt.
 *  Kein Hinweis bei null Positionen; ein Gesamtstatus gilt erst nach erneuter Prüfung. */
export function OutdatedNotice({ count }: { count: number }) {
  const t = useTranslations("HoaWork");
  if (count <= 0) return null;
  return (
    <p role="alert" className={ui.alert} data-testid="audit-outdated-notice">
      {t("audit.outdatedNotice", { n: count })}
    </p>
  );
}
