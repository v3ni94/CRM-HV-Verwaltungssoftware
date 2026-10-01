import { getTranslations } from "next-intl/server";

import { RepresentationList } from "@/components/portal/RepresentationList";
import type { PortalRepresentation } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Vertretungen (M21-05): Vollmachten dieses Zugangs mit Zeitraum und Ablauf, lesend. */
export default async function RepresentationPage() {
  const t = await getTranslations("Representation");
  const res = await serverFetch("/api/v1/portal/representations");
  redirectIfUnauthenticated(res);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = (await res.json()) as { items: PortalRepresentation[] };
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <p className={ui.notice}>{t("intro")}</p>
      <RepresentationList rows={data.items} />
    </div>
  );
}
