import { getTranslations } from "next-intl/server";

import { ContractEditForm } from "@/components/contracts/ContractForm";
import { PageHeader } from "@/components/ui/PageHeader";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

import { loadContractContext } from "../load";

export const dynamic = "force-dynamic";

/** Vertrag bearbeiten (A88): neue Version ab Stichtag, Zahlungsplan ergänzen, Mietvertrag
 *  beenden. Feste Daten werden nur angezeigt (die API kennt kein PATCH auf Verträge). */
export default async function EditContractPage({ params }: { params: Promise<{ id: string }> }) {
  const t = await getTranslations("ContractForm");
  const { id } = await params;
  const [me, ctx] = await Promise.all([getMe(), loadContractContext(id)]);
  const canUpdate = (me.data?.permissions ?? []).includes("contracts:update");

  return (
    <div className={ui.pageGap}>
      <PageHeader
        title={t("page.editTitle")}
        description={ctx ? ctx.contract.number : undefined}
        breadcrumb={[{ href: "/vertraege", label: t("page.list") }, ...(ctx ? [{ href: `/vertraege/${id}`, label: ctx.contract.number }] : []), { label: t("page.edit") }]}
      />
      {!ctx ? (
        <p role="alert" className={ui.alert}>
          {t("page.loadError")}
        </p>
      ) : !canUpdate ? (
        <p role="alert" className={ui.alert}>
          {t("page.noRight")}
        </p>
      ) : (
        <ContractEditForm contract={ctx.contract} partyName={ctx.partyName} unitLabel={ctx.unitLabel} propertyLabel={ctx.propertyLabel} />
      )}
    </div>
  );
}
