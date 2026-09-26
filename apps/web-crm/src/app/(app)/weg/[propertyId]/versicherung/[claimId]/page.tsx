import { getTranslations } from "next-intl/server";

import { ItemForm, StatusSelect } from "@/components/hoa/FinanceForms";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Item = { id: string; kind: string; booking_date: string; amount: string; booked: boolean; note: string | null };
type Claim = {
  title: string;
  damage_date: string;
  insurer: string | null;
  policy_reference: string | null;
  claim_number: string | null;
  deductible: string;
  status: string;
  regress_party: string | null;
  items: Item[];
  totals: Record<string, { booked: string; planned: string }>;
  net_burden_booked: string;
  owner_payments_booked: string;
  document_ids: string[];
  note_text: string;
};
const KINDS = ["damage_cost", "benefit", "deductible", "regress", "owner_payment"];
const STATUS = ["reported", "accepted", "rejected", "settled", "closed"];

export default async function ClaimPage({ params }: { params: Promise<{ propertyId: string; claimId: string }> }) {
  const { propertyId, claimId } = await params;
  const t = await getTranslations("HoaFinance");
  const { data, error, response } = await serverApi().GET("/api/v1/hoa/insurance-claims/{claim_id}", { params: { path: { claim_id: claimId } } });
  redirectIfUnauthenticated(response);
  if (!data) return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  const d = data as unknown as Claim;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader breadcrumb={[{ href: `/weg/${propertyId}`, label: t("claims") }]} title={`${d.title} · ${t(`claimStatus.${d.status}`)}`} />
      <p className={ui.notice}>{d.note_text}</p>
      <p className="text-sm text-muted">
        {t("damageDate")}: {formatDate(d.damage_date)} · {t("insurer")}: {d.insurer ?? "·"} · {t("policy")}: {d.policy_reference ?? "·"} · {t("claimNumber")}: {d.claim_number ?? "·"} · {t("deductible")}: {formatEur(d.deductible)}
      </p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3" data-testid="claim-summary">
        <dt className="text-muted">{t("netBurden")}</dt>
        <dd className="tabular-nums">{formatEur(d.net_burden_booked)}</dd>
        <dt className="text-muted">{t("claimKinds.owner_payment")}</dt>
        <dd className="tabular-nums">{formatEur(d.owner_payments_booked)}</dd>
        <dt className="text-muted">{t("documents", { n: d.document_ids.length })}</dt>
        <dd />
      </dl>
      <div className="overflow-x-auto">
        <table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("itemKind")}</th>
              <th className="num">{t("booked")}</th>
              <th className="num">{t("planned")}</th>
            </tr>
          </thead>
          <tbody>
            {KINDS.map((k) => (
              <tr key={k}>
                <td>{t(`claimKinds.${k}`)}</td>
                <td className="num">{formatEur(d.totals[k]?.booked ?? "0")}</td>
                <td className="num">{formatEur(d.totals[k]?.planned ?? "0")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h2 className={ui.h2}>{t("items")}</h2>
      <div className="overflow-x-auto">
        <table className="mhvp-table">
          <tbody>
            {d.items.map((i) => (
              <tr key={i.id}>
                <td>{formatDate(i.booking_date)}</td>
                <td>{t(`claimKinds.${i.kind}`)}</td>
                <td className="num">{formatEur(i.amount)}</td>
                <td>{i.booked ? t("booked") : t("planned")}</td>
                <td className="text-muted">{i.note ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ItemForm target="insurance-claims" id={claimId} kinds={KINDS} />
      <StatusSelect target="insurance-claims" id={claimId} status={d.status} options={STATUS} group="claimStatus" />
    </div>
  );
}
