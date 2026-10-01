import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { AutomationLevels } from "@/components/banking/AutomationLevels";
import { AutomationSwitch } from "@/components/banking/AutomationSwitch";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Einstellungen, Buchhaltung, Automatikstufen (ADR 0014 Nachtrag S4, Regel M12-05): Stufe je
 *  Fallklasse mit Kennzahlen, Antrag und Freigabe durch zwei Personen, Absenkung sofort. */
export default async function AutomationLevelsPage() {
  const t = await getTranslations("Bank.levels");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("accounting:read")) notFound();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("description")} />
      <AutomationSwitch canApprove={permissions.includes("accounting:approve") && permissions.includes("tenant_settings:update")} userId={me.data?.user_id ?? null} />
      <AutomationLevels canApprove={permissions.includes("accounting:approve")} userId={me.data?.user_id ?? null} />
    </div>
  );
}
