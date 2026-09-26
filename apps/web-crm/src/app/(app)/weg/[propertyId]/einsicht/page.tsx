import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { InspectionRequestCreate } from "@/components/hoa/InspectionRequests";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { hoaContext } from "@/lib/hoa";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Row = { id: string; applicant_contact_id: string; requested_on: string; scope_kinds: string[]; status: string; delivery_kind: string | null };

/** Inspection requests outside the portal (A61): list per community and recording form. */
export default async function InspectionListPage({ params }: { params: Promise<{ propertyId: string }> }) {
  const { propertyId } = await params;
  const [t, th] = await Promise.all([getTranslations("HoaInspection"), getTranslations("Hoa")]);
  const ctx = await hoaContext(propertyId);
  redirectIfUnauthenticated(ctx.response);
  if (!ctx.property || !ctx.entity) return <p role="alert" className={ui.alert}>{th("noEntity")}</p>;
  const base = `/weg/${propertyId}`;
  const res = await serverFetch(`/api/v1/hoa/inspection-requests?legal_entity_id=${encodeURIComponent(ctx.entity.id)}`);
  redirectIfUnauthenticated(res);
  const rows: Row[] = res.ok ? ((await res.json()) as Row[]) : [];
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        breadcrumb={[
          { href: "/weg", label: th("title") },
          { href: base, label: `${ctx.property.number} ${ctx.property.name}` },
        ]}
        title={t("title")}
      />
      <p className={ui.notice}>{t("notice")}</p>
      <div className="overflow-x-auto">
      <table className={ui.table}>
        <thead>
          <tr>
            <th>{t("requestedOn")}</th>
            <th>{t("scope")}</th>
            <th>{t("statusHeading")}</th>
            <th>{t("deliveryKind")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <Link href={`${base}/einsicht/${r.id}`} className="hover:underline">
                  {formatDate(r.requested_on)}
                </Link>
              </td>
              <td>{r.scope_kinds.map((k) => t(`scopeKinds.${k}`)).join(", ")}</td>
              <td>{t(`status.${r.status}`)}</td>
              <td>{r.delivery_kind ? t(`delivery.${r.delivery_kind}`) : ""}</td>
            </tr>
          ))}
          {rows.length === 0 ? (
            <tr>
              <td colSpan={4} className="text-muted">
                {t("empty")}
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
      </div>
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("create")}</h2>
        <InspectionRequestCreate legalEntityId={ctx.entity.id} basePath={base} />
      </section>
    </div>
  );
}
