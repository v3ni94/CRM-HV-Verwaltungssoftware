import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { ImmowareLearning } from "@/components/immoware/ImmowareLearning";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

/** Lernphase Immoware24 (M33, Uebernahme des Moduls Learning aus dem stillgelegten Immoware
 *  Hub): erkundet lesend Struktur und Feldnutzung des DAV-Spiegels je Art und vergleicht mit
 *  dem letzten erfolgreichen Lauf. Kein Schreibpfad, reine Erkenntnisgewinnung. */
export default async function ImmowareLearningPage() {
  const t = await getTranslations("Immoware.learning");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("immoware:read")) notFound();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      <ImmowareLearning canStart={me.data.permissions.includes("immoware:update")} />
    </div>
  );
}
