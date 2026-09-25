import { getTranslations } from "next-intl/server";

import { HandoverCreate } from "@/components/handover/HandoverCreate";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";

export const dynamic = "force-dynamic";

export default async function NewHandoverPage() {
  const t = await getTranslations("Handover");
  const api = serverApi();
  const { data, response } = await api.GET("/api/v1/properties", { params: { query: { page_size: 200 } } });
  redirectIfUnauthenticated(response);
  const properties = ((data as { items?: unknown[] } | undefined)?.items ?? data ?? []) as { id: string; number: string; name: string }[];
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={t("create.title")}
        breadcrumb={[
          { href: "/makler", label: t("broker") },
          { href: "/makler/uebergabe", label: t("title") },
        ]}
      />
      <HandoverCreate properties={properties.map((p) => ({ id: p.id, label: `${p.number} ${p.name}` }))} />
    </div>
  );
}
