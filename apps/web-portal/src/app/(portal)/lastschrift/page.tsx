import { getTranslations } from "next-intl/server";

import { type MandateProposal, SepaMandateForm } from "@/components/portal/SepaMandateForm";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Me = { contracts: { id: string; kind: string; number: string }[] };

/** SEPA-Lastschriftmandat im Portal (M3-02 Portalstufe): Vorschlag mit Textform-Nachweis,
 *  Freigabe im CRM. */
export default async function SepaMandatePage() {
  const t = await getTranslations("SepaMandate");
  const { data, response } = await serverApi().GET("/api/v1/portal/me");
  redirectIfUnauthenticated(response);
  const me = (data ?? { contracts: [] }) as unknown as Me;
  const mineResponse = await serverFetch("/api/v1/portal/sepa-mandates");
  const proposals = mineResponse.status === 200 ? ((await mineResponse.json()) as MandateProposal[]) : [];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <SepaMandateForm contracts={me.contracts} proposals={proposals} />
    </div>
  );
}
