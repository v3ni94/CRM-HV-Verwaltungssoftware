import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { HandoverFill } from "@/components/handover/HandoverFill";
import { HandoverReadCard } from "@/components/handover/HandoverReadCard";
import type { Full } from "@/components/handover/types";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function HandoverFillPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const t = await getTranslations("Handover");
  const { data, error, response } = await serverApi().GET("/api/v1/portal/handover/{protocol_id}", {
    params: { path: { protocol_id: id } },
  });
  redirectIfUnauthenticated(response);
  if (response.status === 404) notFound();
  if (!data) throw new Error(String(error));
  const protocol = data as unknown as Full;
  // A participant in the 14 day read window (right read) gets the read card without a single
  // input element (M31 WP5, scope M30-06); the editor stays for edit grants and for locked
  // protocols of an edit grant (same data, read only fields).
  const readCard = protocol.access.right === "read";
  return (
    <div className={ui.pageGap}>
      <div>
        <Link href="/uebergabe" className="text-sm text-muted underline">
          {t("back")}
        </Link>
        <h1 className={ui.title}>
          {protocol.number}
          {protocol.version > 1 ? ` V${protocol.version}` : ""}
        </h1>
        {protocol.address ? <p className="text-sm text-muted">{protocol.address}</p> : null}
      </div>
      {readCard ? (
        <HandoverReadCard p={protocol} files={`/api/portal-files/portal/handover/${protocol.id}`} />
      ) : (
        <HandoverFill initial={protocol} />
      )}
    </div>
  );
}
