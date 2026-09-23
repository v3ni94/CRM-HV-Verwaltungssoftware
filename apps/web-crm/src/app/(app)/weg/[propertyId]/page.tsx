import { getTranslations } from "next-intl/server";

import { ResolutionTable } from "@/components/hoa/ResolutionTable";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function HoaDetailPage({ params }: { params: Promise<{ propertyId: string }> }) {
  const { propertyId } = await params;
  const t = await getTranslations("Hoa");
  const api = serverApi();
  const { data: prop, error, response } = await api.GET("/api/v1/properties/{property_id}", {
    params: { path: { property_id: propertyId } },
  });
  redirectIfUnauthenticated(response);
  if (!prop) {
    return (
      <p role="alert" className={ui.alert}>
        {problemMessage(error as Problem | undefined, response.status)}
      </p>
    );
  }
  const hoa = prop.legal_entities?.find((e) => e.kind === "hoa");
  const resolutions = hoa
    ? await api.GET("/api/v1/hoa/resolutions", { params: { query: { legal_entity_id: hoa.id } } })
    : null;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">
        {prop.number} {prop.name}
      </h1>
      <h2 className="text-base font-semibold">{t("collection")}</h2>
      {!hoa ? (
        <p className="text-sm text-muted">{t("noEntity")}</p>
      ) : resolutions?.data ? (
        <ResolutionTable rows={resolutions.data as never} />
      ) : (
        <p role="alert" className={ui.alert}>
          {problemMessage(resolutions?.error as Problem | undefined, resolutions?.response.status ?? 500)}
        </p>
      )}
    </div>
  );
}
