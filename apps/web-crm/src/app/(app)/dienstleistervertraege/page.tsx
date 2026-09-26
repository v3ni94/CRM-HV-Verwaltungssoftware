import { getTranslations } from "next-intl/server";

import { ServiceContracts, type ServiceContract } from "@/components/contracts/ServiceContracts";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Dienstleisterverträge (M9-06): Liste und Formular, Kündigungsfristen gehen in die
 *  Fristenliste (A41). Berechnete Termine sind Orientierung und zu prüfen. */
export default async function ServiceContractsPage() {
  const t = await getTranslations("ServiceContracts");
  const api = serverApi();
  const [me, response, contacts, properties] = await Promise.all([
    api.GET("/api/v1/auth/me"),
    serverFetch("/api/v1/service-contracts"),
    api.GET("/api/v1/contacts", { params: { query: { role: "dienstleister", page_size: 200 } } }),
    api.GET("/api/v1/properties", { params: { query: { page_size: 200 } } }),
  ]);
  redirectIfUnauthenticated(response);
  const rows = response.ok ? ((await response.json()) as ServiceContract[]) : null;
  const providers = (contacts.data?.items ?? []).map((c) => ({ id: c.id, label: c.display_name }));
  const propertyItems = ((properties.data as { items?: unknown[] } | undefined)?.items ?? []) as {
    id: string;
    number: string;
    name: string;
  }[];
  const perms = me.data?.permissions ?? [];

  return (
    <div className={ui.pageGap}>
      <PageHeader eyebrow={t("toCheck")} title={t("title")} description={t("description")} />
      {rows === null ? (
        <p role="alert" className={ui.alert}>
          {t("loadError")}
        </p>
      ) : (
        <ServiceContracts
          initial={rows}
          providers={providers}
          properties={propertyItems.map((p) => ({ id: p.id, label: `${p.number} ${p.name}` }))}
          canCreate={perms.includes("contracts:create")}
          canUpdate={perms.includes("contracts:update")}
          canDelete={perms.includes("contracts:delete")}
        />
      )}
    </div>
  );
}
