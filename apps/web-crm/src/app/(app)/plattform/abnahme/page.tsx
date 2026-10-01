import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { AcceptanceRegister, type AcceptanceState } from "@/components/platform/AcceptanceRegister";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Abnahmeregister (V16, AE01): unabhängige Sollwerte je Anhang-D-Fall mit Freigabe durch
 *  eine zweite Person und Abnahmeergebnis. Die Benennung der fachkundigen Person bleibt beim
 *  Betreiber; die Seite öffnet keine Freigabestufe. */
export default async function AcceptancePage() {
  const t = await getTranslations("AE01");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("acceptance:read")) notFound();
  const res = await serverFetch("/api/v1/accounting/acceptance/cases");
  const initial = res.ok ? ((await res.json()) as AcceptanceState) : null;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("description")} />
      <AcceptanceRegister
        initial={initial}
        canManage={permissions.includes("acceptance:manage")}
        canApprove={permissions.includes("acceptance:approve")}
      />
    </div>
  );
}
