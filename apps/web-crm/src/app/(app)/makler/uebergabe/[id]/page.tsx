import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { HandoverEditor } from "@/components/handover/HandoverEditor";
import { HandoverLockedView } from "@/components/handover/HandoverList";
import type { Full } from "@/components/handover/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";

export const dynamic = "force-dynamic";

/** Protocol page (M30, M31 WP2): a locked protocol renders the read view `HandoverSummary`
 *  with versions and actions and never mounts the editor; an open protocol gets the step
 *  editor. */
export default async function HandoverDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const t = await getTranslations("Handover");
  const api = serverApi();
  const { data, error, response } = await api.GET("/api/v1/handover/protocols/{protocol_id}", {
    params: { path: { protocol_id: id } },
  });
  redirectIfUnauthenticated(response);
  if (response.status === 404) notFound();
  if (!data) throw new Error(String(error));
  const protocol = data as unknown as Full;
  return (
    <div className="flex flex-col gap-5 pb-24">
      <PageHeader
        title={`${protocol.number}${protocol.version > 1 ? ` V${protocol.version}` : ""}`}
        description={protocol.address || undefined}
        breadcrumb={[
          { href: "/makler", label: t("broker") },
          { href: "/makler/uebergabe", label: t("title") },
        ]}
      />
      {protocol.locked ? <HandoverLockedView initial={protocol} /> : <HandoverEditor initial={protocol} />}
    </div>
  );
}
