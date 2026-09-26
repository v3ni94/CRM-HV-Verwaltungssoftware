import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { PageHeader } from "@/components/ui/PageHeader";
import { getMe } from "@/lib/me";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import { loadContractContext } from "./load";

export const dynamic = "force-dynamic";

/** Vertragsdetail (A88): feste Daten, aktuelle Version, Zahlungspläne, Link zum Bearbeiten. */
export default async function ContractDetailPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ hinweis?: string }> }) {
  const t = await getTranslations("ContractForm");
  const { id } = await params;
  const { hinweis } = await searchParams;
  const [me, ctx] = await Promise.all([getMe(), loadContractContext(id)]);
  const canUpdate = (me.data?.permissions ?? []).includes("contracts:update");

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
  const { contract, partyName, propertyLabel, unitLabel } = ctx;
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
          <dt className={ui.label}>{t("fields.dunningBlock")}</dt>
          <dd>
            {bool(contract.dunning_block)}
            {contract.dunning_block_reason ? `, ${contract.dunning_block_reason}` : ""}
          </dd>
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
          {contract.notes ? (
            <>
              <dt className={ui.label}>{t("fields.notes")}</dt>
              <dd className="whitespace-pre-line">{contract.notes}</dd>
            </>
          ) : null}
        </dl>
      </section>
      <section className={ui.card}>
        <h2 className={ui.h2}>{t("page.schedules")}</h2>
        {contract.schedules.length === 0 ? (
          <p className={ui.help}>{t("schedule.none")}</p>
        ) : (
          <ul className="text-sm">
            {contract.schedules.map((s) => (
              <li key={s.id}>
                {t(`intervals.${s.interval}`)}, {t(`dueDayRules.${s.due_day_rule}`)} {s.due_day}, {t("schedule.from")} {formatDate(s.valid_from)}
                {s.valid_to ? ` ${t("schedule.to")} ${formatDate(s.valid_to)}` : ""}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
