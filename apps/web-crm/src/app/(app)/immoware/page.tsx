import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { ImmowareBrowser } from "@/components/immoware/ImmowareBrowser";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

/** Immoware24-Spiegel (M32): Dokumente, Kontakte und Termine, gelesen per WebDAV, CardDAV und
 *  CalDAV. Immoware24 bleibt Master, es gibt keinen Schreibpfad in dieser Ansicht. */
export default async function ImmowarePage() {
  const t = await getTranslations("Immoware");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("immoware:read")) notFound();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      <ImmowareBrowser />
    </div>
  );
}
