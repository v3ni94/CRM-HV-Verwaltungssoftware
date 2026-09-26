import { getTranslations } from "next-intl/server";

import { ContractCreateForm, type PropertyOption } from "@/components/contracts/ContractForm";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Vertrag anlegen (A88): Objekt- und Einheitenauswahl, Vertragspartner per Kontaktsuche,
 *  Laufzeit, Eigentumsangaben, Zahlung, Zahlungsplan und Kaution. Speichern per BFF. */
export default async function NewContractPage({ searchParams }: { searchParams: Promise<{ objekt?: string; einheit?: string }> }) {
  const t = await getTranslations("ContractForm");
  const params = await searchParams;
  const [me, response] = await Promise.all([getMe(), serverFetch("/api/v1/properties?page_size=500")]);
  redirectIfUnauthenticated(response);
  const page = response.ok ? ((await response.json()) as { items: { id: string; number: string; name: string; management_type: PropertyOption["management_type"] }[] }) : null;
  const properties: PropertyOption[] = (page?.items ?? []).map((p) => ({ id: p.id, label: `${p.number} ${p.name}`, management_type: p.management_type }));
  const canCreate = (me.data?.permissions ?? []).includes("contracts:create");

  return (
    <div className={ui.pageGap}>
      <PageHeader title={t("page.new")} description={t("page.newDescription")} breadcrumb={[{ href: "/vertraege", label: t("page.list") }, { label: t("page.new") }]} />
      {canCreate ? (
        <ContractCreateForm properties={properties} initialPropertyId={params.objekt} initialUnitId={params.einheit} />
      ) : (
        <p role="alert" className={ui.alert}>
          {t("page.noRight")}
        </p>
      )}
    </div>
  );
}
