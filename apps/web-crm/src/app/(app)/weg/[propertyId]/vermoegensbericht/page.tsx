import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { AssetReportCreate } from "@/components/hoa/AssetReportForms";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { hoaContext } from "@/lib/hoa";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Row = { id: string; as_of: string; status: string; snapshot_hash: string | null };

/** M24-02: asset reports of the community per reporting date (W11), drafts behind G4. */
export default async function AssetReportListPage({ params }: { params: Promise<{ propertyId: string }> }) {
  const { propertyId } = await params;
  const [t, tf] = await Promise.all([getTranslations("Hoa"), getTranslations("HoaFinance")]);
  const ctx = await hoaContext(propertyId);
  redirectIfUnauthenticated(ctx.response);
  if (!ctx.property || !ctx.entity) return <p role="alert" className={ui.alert}>{t("noEntity")}</p>;
  const base = `/weg/${propertyId}`;
  const response = ctx.ledger ? await serverFetch(`/api/v1/hoa/asset-reports?ledger_id=${encodeURIComponent(ctx.ledger.id)}`) : null;
  const rows = response?.ok ? ((await response.json()) as Row[]) : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader breadcrumb={[{ href: base, label: `${ctx.property.number} ${ctx.property.name}` }]} title={tf("assetReports")} />
      <p className={ui.notice}>{tf("assetReportNotice")}</p>
      {rows.length === 0 ? <p className="text-sm text-muted">{tf("assetReportNone")}</p> : null}
      <ul className="text-sm" data-testid="asset-report-list">
        {rows.map((r) => (
          <li key={r.id}>
            <Link href={`${base}/vermoegensbericht/${r.id}`} className="hover:underline">
              {formatDate(r.as_of)} · {tf(`assetStatus.${r.status}`)}
            </Link>
          </li>
        ))}
      </ul>
      {ctx.ledger ? <AssetReportCreate ledgerId={ctx.ledger.id} basePath={base} /> : null}
    </div>
  );
}
