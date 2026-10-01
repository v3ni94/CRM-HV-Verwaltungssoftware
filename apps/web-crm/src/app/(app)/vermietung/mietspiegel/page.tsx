import { getTranslations } from "next-intl/server";

import { RentIndexAdmin, type RentIndexRow } from "@/components/letting/RentIndexAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function RentIndexPage() {
  const t = await getTranslations("LettingW3.rentIndex");
  const tl = await getTranslations("Letting");
  const api = serverApi();
  const [me, { data, error, response }] = await Promise.all([getMe(), api.GET("/api/v1/letting/rent-index")]);
  redirectIfUnauthenticated(response);
  if (!data) return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  const permissions = me.data?.permissions ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/vermietung", label: tl("title") }]} title={t("title")} />
      <RentIndexAdmin rows={data as unknown as RentIndexRow[]} canEdit={permissions.includes("contracts:update")} />
    </div>
  );
}
