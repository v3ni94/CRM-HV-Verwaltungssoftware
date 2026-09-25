import { getTranslations } from "next-intl/server";

import { MeterReadingForm } from "@/components/meters/MeterReadingForm";
import { redirectIfUnauthenticated, serverGet } from "@/lib/api-server";
import type { PortalMe } from "@/lib/portal";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function MeterPage() {
  const t = await getTranslations("Meter");
  const { response } = await serverGet<PortalMe>("/api/v1/portal/me");
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className={ui.title}>{t("title")}</h1>
        <p className="mt-3 max-w-xl text-sm text-muted">{t("intro")}</p>
      </div>
      <MeterReadingForm />
    </div>
  );
}
