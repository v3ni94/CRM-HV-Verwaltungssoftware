import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { AuditLogPanel } from "@/components/common/AuditLogPanel";
import { EntityLinksBar } from "@/components/common/EntityLinksBar";
import { AllocationAgreementsPanel } from "@/components/contracts/AllocationAgreementsPanel";
import { AmountsPanel } from "@/components/contracts/AmountsPanel";
import { ContractAllocationValues } from "@/components/contracts/ContractAllocationValues";
import { ContractDebtorAccount } from "@/components/contracts/ContractDebtorAccount";
import { ContractIndexTermsPanel } from "@/components/contracts/ContractIndexTermsPanel";
import { ContractCustomFieldsForm } from "@/components/aj17/ContractCustomFieldsForm";
import { ContractNotesSection } from "@/components/contracts/ContractNotesSection";
import { ContractMandates } from "@/components/contracts/ContractMandates";
import { ContractVersionHistory } from "@/components/contracts/ContractVersionHistory";
import { DepositInterestPanel } from "@/components/contracts/DepositInterestPanel";
import { DepositPanel } from "@/components/contracts/DepositPanel";
import { SchedulePanel } from "@/components/contracts/SchedulePanel";
import { OwnershipTransfer } from "@/components/contracts/OwnershipTransfer";
import { RentInvoicePanel } from "@/components/contracts/RentInvoicePanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { DeadlineCreatePanel } from "@/components/workspace/DeadlineCreatePanel";
import { getMe } from "@/lib/me";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import { loadContractContext } from "./load";

export const dynamic = "force-dynamic";

/** Vertragsdetail (A88): feste Daten, aktuelle Version, Zahlungspläne, Link zum Bearbeiten. */
export default async function ContractDetailPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ hinweis?: string }> }) {
  const t = await getTranslations("ContractForm");
  const ta = await getTranslations("ContractApproval");
  const { id } = await params;
  const { hinweis } = await searchParams;
  const [me, ctx] = await Promise.all([getMe(), loadContractContext(id)]);
  const canUpdate = (me.data?.permissions ?? []).includes("contracts:update");
  const permissions = me.data?.permissions ?? [];

  if (!ctx) {
    return (
      <div className={ui.pageGap}>
        <PageHeader title={t("page.detail")} breadcrumb={[{ href: "/vertraege", label: t("page.list") }]} />
        <p role="alert" className={ui.alert}>
          {t("page.loadError")}
        </p>
      </div>
    );
  }
  const { contract, amounts, paymentTypes, deposits, settlements, rates, partyName, propertyLabel, unitLabel, allocationValues, allocationKeys, mandates, ledger, meterLabels, terminationReadings, managementType } = ctx;
  const bool = (v: boolean) => (v ? t("yes") : t("no"));

  return (
    <div className={ui.pageGap}>
      <PageHeader
        eyebrow={t(`kinds.${contract.kind}`)}
        title={`${t("page.detail")} ${contract.number}`}
        description={t("edit.version", { n: contract.version })}
        breadcrumb={[{ href: "/vertraege", label: t("page.list") }, { label: contract.number }]}
        action={
          canUpdate ? (
            <Link href={`/vertraege/${contract.id}/bearbeiten`} className={ui.primary}>
              {t("page.edit")}
            </Link>
          ) : null
        }
      />
      <EntityLinksBar
        links={[
          { type: "property", id: contract.property_id, label: propertyLabel },
          { type: "unit", id: contract.unit_id, label: unitLabel },
          { type: "contact", id: contract.party_id, label: partyName },
          { type: "ledger", id: ledger?.id ?? null, label: ledger?.name ?? null },
          { type: "ticket", href: `/tickets?unit_id=${contract.unit_id}`, label: t("links.tickets") },
        ]}
      />
      {contract.approval_status === "pending" ? (
        <p role="status" className={ui.notice} data-testid="approval-pending">
          <span className={ui.badgeWarning}>{ta("pendingBadge")}</span>{" "}
          <Link href="/vertraege/freigabe" className="hover:underline">
            {ta("link")}
          </Link>
        </p>
      ) : contract.approval_status === "rejected" ? (
        <p role="status" className={ui.notice}>
          <span className={ui.badgeDanger}>{ta("rejectedBadge")}</span>
        </p>
      ) : null}
      {hinweis ? (
        <p role="status" className={ui.notice}>
          {t("page.notice")}: {hinweis}
        </p>
      ) : null}
      <section className={ui.card}>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <dt className={ui.label}>{t("fields.property")}</dt>
          <dd>{propertyLabel}</dd>
          <dt className={ui.label}>{t("fields.unit")}</dt>
          <dd>{unitLabel}</dd>
          <dt className={ui.label}>{t("fields.party")}</dt>
          <dd>
            <Link href={`/kontakte/${contract.party_id}`} className="hover:underline">
              {partyName}
            </Link>
          </dd>
          <dt className={ui.label}>{t("fields.startDate")}</dt>
          <dd>{formatDate(contract.start_date)}</dd>
          <dt className={ui.label}>{t("fields.endDate")}</dt>
          <dd>{contract.end_date ? formatDate(contract.end_date) : t("edit.openEnd")}</dd>
          {contract.termination_date ? (
            <>
              <dt className={ui.label}>{t("termination.terminationDate")}</dt>
              <dd>
                {formatDate(contract.termination_date)}
                {contract.termination_reason ? `, ${contract.termination_reason}` : ""}
              </dd>
            </>
          ) : null}
          <dt className={ui.label}>{t("fields.vatOption")}</dt>
          <dd>{t(`vatOptions.${contract.vat_option}`)}</dd>
          <dt className={ui.label}>{t("fields.directDebit")}</dt>
          <dd>{bool(contract.direct_debit)}</dd>
          {contract.kind === "tenancy" ? (
            <>
              <dt className={ui.label}>{t("fields.rentIncreaseBlockUntil")}</dt>
              <dd>{contract.rent_increase_block_until ? formatDate(contract.rent_increase_block_until) : t("no")}</dd>
              <dt className={ui.label}>{t("fields.userChangeFee")}</dt>
              <dd>{bool(contract.user_change_fee)}</dd>
              <dt className={ui.label}>{t("fields.allocationLossRisk")}</dt>
              <dd>{bool(contract.allocation_loss_risk)}</dd>
            </>
          ) : (
            <>
              <dt className={ui.label}>{t("fields.titleTransferDate")}</dt>
              <dd>{formatDate(contract.title_transfer_date)}</dd>
              <dt className={ui.label}>{t("fields.benefitBurdenDate")}</dt>
              <dd>{contract.benefit_burden_date ? formatDate(contract.benefit_burden_date) : t("no")}</dd>
              <dt className={ui.label}>{t("fields.acquisitionKind")}</dt>
              <dd>{contract.acquisition_kind ? t(`acquisitionKinds.${contract.acquisition_kind}`) : t("no")}</dd>
              <dt className={ui.label}>{t("fields.sevEnabled")}</dt>
              <dd>{bool(contract.sev_enabled)}</dd>
              <dt className={ui.label}>{t("fields.specialSuccessionLiability")}</dt>
              <dd>{bool(contract.special_succession_liability)}</dd>
            </>
          )}
        </dl>
      </section>
      <ContractNotesSection contract={contract} canEdit={canUpdate} />
      <ContractCustomFieldsForm contractId={contract.id} initial={((contract as unknown as { custom_fields?: Record<string, unknown> }).custom_fields ?? {})} canEdit={canUpdate} />
      {contract.kind === "ownership" && !contract.end_date ? (
        <OwnershipTransfer contractId={contract.id} sevAllowed={managementType === "hoa_with_sev"} canUpdate={canUpdate} />
      ) : null}
      <AmountsPanel contractId={contract.id} amounts={amounts} paymentTypes={paymentTypes} canUpdate={canUpdate} startDate={contract.start_date} endDate={contract.end_date} />
      <SchedulePanel contractId={contract.id} schedules={contract.schedules} canUpdate={canUpdate} />
      <ContractAllocationValues contractId={contract.id} values={allocationValues} keys={allocationKeys} canUpdate={canUpdate} startDate={contract.start_date} />
      <ContractMandates mandates={mandates} defaultMandateId={contract.sepa_mandate_id} directDebit={contract.direct_debit} canUpdate={canUpdate} />
      {contract.debtor_account ? (
        <ContractDebtorAccount
          account={contract.debtor_account}
          ledgerId={ledger?.id ?? null}
          ledgerName={ledger?.name ?? null}
          moveInOn={contract.move_in_on}
          moveOutOn={contract.move_out_on}
          readings={terminationReadings}
          meterLabels={meterLabels}
        />
      ) : null}
      {contract.kind === "tenancy" ? (
        <DepositPanel deposits={deposits} settlements={settlements} rates={rates} contractEndDate={contract.end_date} canUpdate={canUpdate} contractId={contract.id} />
      ) : null}
      {contract.kind === "tenancy"
        ? deposits.map((deposit) => <DepositInterestPanel key={deposit.id} depositId={deposit.id} canUpdate={canUpdate} />)
        : null}
      {contract.kind === "tenancy" ? <ContractIndexTermsPanel contractId={contract.id} canUpdate={canUpdate} /> : null}
      {contract.kind === "tenancy" ? <AllocationAgreementsPanel contractId={contract.id} propertyId={contract.property_id} canUpdate={canUpdate} /> : null}
      {contract.kind === "tenancy" ? <RentInvoicePanel contractId={contract.id} vatOption={contract.vat_option} canUpdate={canUpdate} canSettings={permissions.includes("tenant_settings:update")} /> : null}
      {permissions.includes("tickets:read") ? (
        <DeadlineCreatePanel sourceType="contract" sourceId={contract.id} canCreate={permissions.includes("tickets:create")} canUpdate={permissions.includes("tickets:update")} />
      ) : null}
      <ContractVersionHistory contractId={contract.id} />
      <AuditLogPanel entityType="contract" entityId={contract.id} />
    </div>
  );
}
