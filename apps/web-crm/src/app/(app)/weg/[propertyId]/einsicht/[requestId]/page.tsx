import { getTranslations } from "next-intl/server";

import { InspectionPanel, type CandidateDocument, type InspectionRequest } from "@/components/hoa/InspectionPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Detail = InspectionRequest & { legal_entity_id: string; applicant_contact_id: string; requested_on: string; scope_kinds: string[]; scope_text: string | null };

/** One inspection request (A61): status steps, notes, package with checksums, download. */
export default async function InspectionDetailPage({ params }: { params: Promise<{ propertyId: string; requestId: string }> }) {
  const { propertyId, requestId } = await params;
  const t = await getTranslations("HoaInspection");
  const res = await serverFetch(`/api/v1/hoa/inspection-requests/${encodeURIComponent(requestId)}`);
  redirectIfUnauthenticated(res);
  if (!res.ok) return <p role="alert" className={ui.alert}>{t("notFound")}</p>;
  const request = (await res.json()) as Detail;
  const api = serverApi();
  const [applicant, docs] = await Promise.all([
    api.GET("/api/v1/contacts/{contact_id}/name", { params: { path: { contact_id: request.applicant_contact_id } } }),
    serverFetch(`/api/v1/hoa/inspection-requests/${encodeURIComponent(requestId)}/candidates`),
  ]);
  const documents: CandidateDocument[] = docs.ok ? ((await docs.json()) as CandidateDocument[]) : [];
  const base = `/weg/${propertyId}`;
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        breadcrumb={[
          { href: "/weg", label: t("hoa") },
          { href: `${base}/einsicht`, label: t("title") },
        ]}
        title={`${t("request")} ${formatDate(request.requested_on)}`}
        description={`${t("applicant")}: ${String(applicant.data?.display_name ?? request.applicant_contact_id)}`}
      />
      <p className="text-sm">
        <span className={ui.label}>{t("scope")}</span> {request.scope_kinds.map((k) => t(`scopeKinds.${k}`)).join(", ")}
        {request.scope_text ? ` · ${request.scope_text}` : ""}
      </p>
      <InspectionPanel request={request} documents={documents} />
    </div>
  );
}
