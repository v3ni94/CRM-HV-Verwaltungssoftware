import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { G1OpeningChecklist, type G1OpeningState } from "@/components/settings/G1OpeningChecklist";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Einstellungen, Buchhaltung, G1 Öffnung (M12-09): Checkliste vor der produktiven Buchführung
 *  mit Stand aus dem System (Kontenrahmen, Anhang D Fälle, Automatikstufen, Freigabestufe),
 *  Ergebnis je Prüfpunkt und dem Antrag auf G1 über den bestehenden Vier-Augen-Pfad. Die
 *  Seite öffnet die Stufe nie selbst. */
export default async function G1OpeningPage() {
  const t = await getTranslations("G1Opening");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("accounting:read")) notFound();
  const res = await serverFetch("/api/v1/accounting/g1-opening");
  const initial = res.ok ? ((await res.json()) as G1OpeningState) : null;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("description")} />
      <G1OpeningChecklist
        initial={initial}
        canRecord={permissions.includes("accounting:approve")}
        canRequest={permissions.includes("release_gates:create")}
      />
    </div>
  );
}
