import { getTranslations } from "next-intl/server";

import { ListingCreate } from "@/components/letting/ListingCreate";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function NewListingPage() {
  const t = await getTranslations("Broker.create");
  const api = serverApi();
  const { data, response } = await api.GET("/api/v1/properties", { params: { query: { page_size: 200 } } });
  redirectIfUnauthenticated(response);
  const properties = (data?.items ?? data ?? []) as { id: string; number: string; name: string }[];
  return (
    <div className="flex flex-col gap-5">
      <h1 className={ui.title}>{t("title")}</h1>
      <ListingCreate properties={properties.map((p) => ({ id: p.id, label: `${p.number} ${p.name}` }))} />
    </div>
  );
}
