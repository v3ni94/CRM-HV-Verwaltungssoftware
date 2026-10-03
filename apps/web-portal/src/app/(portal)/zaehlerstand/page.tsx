import { getTranslations } from "next-intl/server";

import { MeterReadingForm, type MeterPhotoMode } from "@/components/portal/MeterReadingForm";
import type { Me } from "@/components/portal/types";
import { serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function MeterPage() {
  const t = await getTranslations("Meter");
  // AN02 (GAJ-401): Mandantenschalter meter_photo_mode; ohne Antwort gilt der Standard hint.
  const { data: meData } = await serverApi().GET("/api/v1/portal/me");
  const me = (meData ?? null) as unknown as Me | null;
  const photoMode: MeterPhotoMode = me?.features?.meter_photo_mode ?? "hint";
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <MeterReadingForm photoMode={photoMode} />
    </div>
  );
}
